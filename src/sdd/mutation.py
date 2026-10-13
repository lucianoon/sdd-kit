"""Sensor de discriminação determinístico: os testes pegam o código errado?

Injeta uma falha de comportamento por vez (troca de operador) numa cópia isolada do
projeto e roda os testes. Mutante que sobrevive = os testes não distinguem o código
certo do errado naquele ponto. Agnóstico: opera sobre texto e só lê o exit code.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .core import Project
from .diff import matches

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
        in_docstring = False
        for n, line in enumerate(lines, 1):
            s = line.strip()
            # docstrings Python de várias linhas
            if s.count('"""') % 2 == 1 or s.count("'''") % 2 == 1:
                in_docstring = not in_docstring
                continue
            if in_docstring or not s or s.startswith(COMMENT_STARTS) or SKIP_MARK in line:
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
    ignore_always = {".git", ".sdd", "__pycache__", ".pytest_cache", ".mypy_cache"}

    def ignore(d, names):
        return [n for n in names if n in ignore_always or n in link or n.endswith(".egg-info")]

    shutil.copytree(root, dest, ignore=ignore, symlinks=True)
    for name in link:  # dependências pesadas: referência, não cópia
        if (root / name).exists():
            (dest / name).symlink_to((root / name).resolve())
    return dest


def _run(cmd: str, cwd: Path, env: dict, timeout: int) -> str:
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True, timeout=timeout)
        return "passed" if p.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        return "timeout"


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
    work = _copy_project(proj.root, cfg.link)
    try:
        env = {**os.environ, **{k: v.replace("{root}", str(work)) for k, v in cfg.env.items()}}
        if _run(cmd, work, env, cfg.timeout) != "passed":
            rep.error = "a suíte não passa sem mutações; corrija os testes antes de medir"
            rep.mutants = []
            return rep
        for m in rep.mutants:
            target = work / m.file
            original = target.read_text(encoding="utf-8")
            lines = original.splitlines(keepends=True)
            nl = lines[m.line - 1][len(lines[m.line - 1].rstrip("\r\n")):]
            lines[m.line - 1] = m.mutated + nl
            target.write_text("".join(lines), encoding="utf-8")
            try:
                result = _run(cmd, work, env, cfg.timeout)
            finally:
                target.write_text(original, encoding="utf-8")
            m.status = {"failed": "killed", "passed": "survived", "timeout": "timeout"}[result]
            if on_result:
                on_result(m)
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)
    return rep


def render_markdown(reports: list[MutationReport]) -> str:
    out = ["# Relatório de mutação SDD", ""]
    for r in reports:
        status = "ERRO" if r.error else ("APROVADO" if r.ok else "REPROVADO")
        out.append(f"## {r.feature}: {status}")
        if r.error:
            out += ["", r.error, ""]
            continue
        out += ["", f"Score {r.score:.0%} (mínimo {r.min_score:.0%}): {r.killed}/{len(r.mutants)} "
                f"mutantes mortos, amostrados de {r.candidates} candidatos.", ""]
        surv = [m for m in r.mutants if m.status == "survived"]
        if surv:
            out += ["| Onde | Operador | Linha mutada |", "|---|---|---|"]
            out += [f"| `{m.where}` | {m.operator} | `{m.mutated.strip()}` |" for m in surv]
            out.append("")
    return "\n".join(out) + "\n"
