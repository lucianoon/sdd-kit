"""Sensor de discriminação determinístico: os testes pegam o código errado?

Injeta uma falha de comportamento por vez (troca de operador) numa cópia isolada do
projeto e roda os testes. Mutante que sobrevive = os testes não distinguem o código
certo do errado naquele ponto. Agnóstico: opera sobre texto e só lê o exit code.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .core import Project
from .diff import matches
from .procs import run_shell
from .textscan import python_string_lines

# (nome, padrão, substituição). Lookarounds evitam ->, =>, <<, ++, +=, etc.
OPERATORS: list[tuple[str, re.Pattern, str]] = [
    (name, re.compile(pat), rep) for name, pat, rep in [
        ("==→!=", r"==(?!=)", "!="),
        ("!=→==", r"!=(?!=)", "=="),
        ("<=→>", r"<=", ">"),
        (">=→<", r"(?<![=>])>=", "<"),
        ("<→>=", r"(?<![<=!-])<(?![<=-])", ">="),
        (">→<=", r"(?<![->=<])>(?![>=])", "<="),
        ("&&→||", r"&&", "||"),
        ("||→&&", r"\|\|", "&&"),
        ("and→or", r"\band\b", "or"),
        ("or→and", r"\bor\b", "and"),
        ("True→False", r"\bTrue\b", "False"),
        ("False→True", r"\bFalse\b", "True"),
        ("true→false", r"\btrue\b", "false"),
        ("false→true", r"\bfalse\b", "true"),
        ("+→-", r"(?<![+\de])\+(?![+=])", "-"),
        ("-→+", r"(?<![-\de])-(?![->=])", "+"),
    ]
]
SKIP_MARK = "sdd: no-mutate"
COMMENT_STARTS = ("#", "//", "*", "/*", "--")


@dataclass
class Mutant:
    file: str
    line: int
    col: int
    operator: str
    original: str
    mutated: str
    status: str = "pending"  # killed | survived | timeout

    @property
    def where(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass
class MutationReport:
    feature: str
    mutants: list[Mutant] = field(default_factory=list)
    candidates: int = 0
    min_score: float = 0.8
    error: str | None = None

    @property
    def killed(self) -> int:
        return sum(m.status in ("killed", "timeout") for m in self.mutants)

    @property
    def score(self) -> float:
        return self.killed / len(self.mutants) if self.mutants else 1.0

    @property
    def ok(self) -> bool:
        return self.error is None and self.score >= self.min_score

    @property
    def verdict(self) -> str:
        if self.error:
            return "ERRO"
        if not self.mutants:
            return "NÃO_APLICÁVEL"
        return "APROVADO" if self.ok else "REPROVADO"


def _code_region(line: str) -> int:
    """Índice onde começa um comentário de fim de linha fora de string (ou len)."""
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "#" or line.startswith("//", i):
            return i
        i += 1
    return len(line)


def _in_string(line: str, pos: int) -> bool:
    quote = None
    i = 0
    while i < pos:
        c = line[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        i += 1
    return quote is not None


def candidates(root: Path, files: list[str]) -> list[Mutant]:
    out: list[Mutant] = []
    for rel in files:
        try:
            lines = (root / rel).read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        in_string = (python_string_lines("\n".join(lines) + "\n")
                     if rel.endswith(".py") else set())
        for n, line in enumerate(lines, 1):
            s = line.strip()
            if n in in_string or not s or s.startswith(COMMENT_STARTS) or SKIP_MARK in line:
                continue
            if s.startswith(("import ", "from ", "#include", "package ", "using ")):
                continue
            end = _code_region(line)
            for name, pat, rep in OPERATORS:
                for m in pat.finditer(line, 0, end):
                    if not _in_string(line, m.start()):
                        mutated = line[:m.start()] + rep + line[m.end():]
                        out.append(Mutant(rel, n, m.start() + 1, name, line, mutated))
    return out


def sample(items: list[Mutant], k: int) -> list[Mutant]:
    """Amostra determinística e espalhada (sem aleatoriedade: reprodutível no CI)."""
    if len(items) <= k:
        return items
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def _copy_project(root: Path, link: list[str]) -> Path:
    dest = Path(tempfile.mkdtemp(prefix="sdd-mutate-")) / "p"
    ignore_always = {".git", ".sdd", ".sdd-tmp", "__pycache__", ".pytest_cache", ".mypy_cache"}

    def ignore(d, names):
        return [n for n in names if n in ignore_always or n in link or n.endswith(".egg-info")]

    try:
        shutil.copytree(root, dest, ignore=ignore, symlinks=True)
    except BaseException:
        shutil.rmtree(dest.parent, ignore_errors=True)  # não copiando inteiro, não deixa lixo
        raise
    for name in link:  # dependências pesadas: referência, não cópia
        if (root / name).exists():
            (dest / name).symlink_to((root / name).resolve())
    return dest


def sweep_stale(max_age: float = 24 * 3600) -> int:
    """Remove cópias de trabalho órfãs de runs anteriores (ex.: sdd morto à força).

    Só toca em diretórios com o prefixo próprio de mutate e mais velhos que `max_age`
    (24 h): uma execução concorrente legítima nunca é apagada.
    """
    removed = 0
    for d in Path(tempfile.gettempdir()).glob("sdd-mutate-*"):
        try:
            if d.is_dir() and time.time() - d.stat().st_mtime >= max_age:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


class _Clock:
    """mtimes estritamente crescentes: toda escrita invalida caches baseados em data."""

    def __init__(self):
        self.t = time.time()

    def next(self) -> float:
        self.t = max(self.t + 2, time.time())
        return self.t


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:  # preserva \r\n exatamente
        return f.read()


def _write(path: Path, text: str, clock: _Clock) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    t = clock.next()
    os.utime(path, (t, t))


def _run(cmd: str, cwd: Path, env: dict, timeout: int) -> str:
    r = run_shell(cmd, cwd, timeout, env)
    if r.timed_out:
        return "timeout"
    return "passed" if r.returncode == 0 else "failed"


def feature_files(proj: Project, spec, only: set[str] | None = None) -> list[str]:
    exts = tuple(proj.config.mutation.extensions)
    out = []
    for p in sorted(proj.root.rglob("*")):
        if not p.is_file() or not p.name.endswith(exts):
            continue
        rel = p.relative_to(proj.root).as_posix()
        if rel.startswith((".git/", ".sdd/")) or not matches(rel, spec.paths):
            continue
        if only is None or rel in only:
            out.append(rel)
    return out


def run_feature(proj: Project, spec, only: set[str] | None = None,
                max_mutants: int | None = None, on_result=None) -> MutationReport:
    cfg = proj.config.mutation
    rep = MutationReport(feature=spec.feature, min_score=cfg.min_score)
    if not spec.paths:
        rep.error = "spec sem `paths`: não há código para mutar"
        return rep
    cands = candidates(proj.root, feature_files(proj, spec, only))
    rep.candidates = len(cands)
    rep.mutants = sample(cands, max_mutants or cfg.max_mutants)
    if not rep.mutants:
        return rep

    cmd = cfg.command or proj.config.tests.command
    sweep_stale()  # órfãos de execuções mortas não se acumulam no disco
    work = _copy_project(proj.root, cfg.link)
    clock = _Clock()
    try:
        env = {**os.environ, **{k: v.replace("{root}", str(work)) for k, v in cfg.env.items()}}
        private_tmp = work / ".sdd-tmp"
        private_tmp.mkdir()
        # Autotestes do sweep, inclusive mutados, só enxergam temporários desta cópia.
        env.update({key: str(private_tmp) for key in ("TMPDIR", "TEMP", "TMP")})
        # Bytecode em cache faria o Python rodar o código antigo quando a mutação não muda o
        # tamanho do arquivo (ex.: + → -) e ocorre no mesmo segundo: falso sobrevivente.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if _run(cmd, work, env, cfg.timeout) != "passed":
            rep.error = "a suíte não passa sem mutações; corrija os testes antes de medir"
            rep.mutants = []
            return rep
        for m in rep.mutants:
            target = work / m.file
            try:
                original = _read(target)
            except OSError:
                rep.error = "cópia de trabalho indisponível; execução de mutação incompleta"
                break
            lines = original.splitlines(keepends=True)
            nl = lines[m.line - 1][len(lines[m.line - 1].rstrip("\r\n")):]
            lines[m.line - 1] = m.mutated + nl
            _write(target, "".join(lines), clock)
            try:
                result = _run(cmd, work, env, cfg.timeout)
            finally:
                try:
                    _write(target, original, clock)
                except OSError:
                    rep.error = "cópia de trabalho indisponível; execução de mutação incompleta"
            m.status = {"failed": "killed", "passed": "survived", "timeout": "timeout"}[result]
            if on_result:
                on_result(m)
            if rep.error:
                break
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)  # sdd: no-mutate (proteção; rmtree normal não falha)
    return rep


def render_markdown(reports: list[MutationReport], constitution=None, scope=None) -> str:
    from .report import metadata, version_line, constitution_section

    out = ["# Relatório de mutação SDD", "", version_line(metadata("mutate")), ""]
    if scope:
        out += [f"Features: {', '.join(scope['features'])}. Base: {scope['base'] or 'projeto inteiro'}.", ""]
    for r in reports:
        status = r.verdict
        out.append(f"## {r.feature}: {status}")
        if r.error:
            out += ["", r.error, ""]
            continue
        if not r.mutants:
            out += ["", "Nenhum candidato a mutação neste alcance.", ""]
            continue
        out += ["", f"Score {r.score:.0%} (mínimo {r.min_score:.0%}): {r.killed}/{len(r.mutants)} "
                f"mutantes mortos, amostrados de {r.candidates} candidatos.", ""]
        surv = [m for m in r.mutants if m.status == "survived"]
        if surv:
            out += ["| Onde | Operador | Linha mutada |", "|---|---|---|"]
            out += [f"| `{m.where}` | {m.operator} | `{m.mutated.strip()}` |" for m in surv]
            out.append("")
    out += constitution_section(constitution)
    return "\n".join(out) + "\n"
