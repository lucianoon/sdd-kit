"""Sensor de discriminação determinístico: os testes pegam o código errado?

Injeta uma falha de comportamento por vez (troca de operador) numa cópia isolada do
projeto e roda os testes. Mutante que sobrevive = os testes não distinguem o código
certo do errado naquele ponto. Agnóstico: opera sobre texto e só lê o exit code; a
extensão do arquivo decide comentário, aspas, generics, JSX e quais operadores valem.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .project import Project
from .diff import matches
from .procs import run_shell
from .textscan import python_string_lines

HASH = (".py", ".rb")
C_LIKE = (".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".kt", ".cs", ".rs", ".c", ".cc", ".cpp",
          ".swift", ".scala")
BACKTICK = (".js", ".jsx", ".ts", ".tsx", ".go")
GENERICS = (".ts", ".tsx", ".java", ".kt", ".cs", ".rs", ".cc", ".cpp", ".swift", ".scala")
JSX = (".jsx", ".tsx")
NULL = {".py": "None", ".js": "undefined", ".jsx": "undefined", ".ts": "undefined", ".tsx": "undefined"}
BANG = C_LIKE + (".php",)
SKIP_MARK = "sdd: no-mutate"
COMMENT_STARTS = ("#", "//", "*", "/*", "--")  # extensão desconhecida: todos os marcadores


def syntax(ext: str) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """(marcadores de comentário de fim de linha, inícios de linha de comentário, aspas)."""
    if ext in HASH:  # em Python, // é divisão inteira
        return ("#",), ("#",), "\"'"
    if ext == ".php":
        return ("#", "//"), ("#", "//", "*", "/*"), "\"'"
    if ext in C_LIKE:  # em JS/TS, # é campo privado
        return ("//",), ("//", "*", "/*"), "\"'" + ("`" if ext in BACKTICK else "")
    return ("#", "//"), COMMENT_STARTS, "\"'`"


def _plus_one(m: re.Match, line: str, ext: str) -> str | None:
    s = m.group(0)
    return None if len(s) > 1 and s.startswith("0") else str(int(s) + 1)  # 0755 é octal em Go/C


def _not_for_in(m: re.Match, line: str, ext: str) -> str | None:
    """O `in` de `for x in` faz parte do laço; trocar por `not in` só quebraria a sintaxe."""
    return None if re.search(r"\bfor\b(?:(?!\bin\b).)*$", line[:m.start()]) else "not in"


def _balanced(text: str) -> bool:
    depth, quote, i = 0, None, 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0 and quote is None


def _null_return(m: re.Match, line: str, ext: str) -> str | None:
    """`return <expr>` de uma linha vira o nulo da linguagem; o de várias linhas é preservado."""
    expr = m["e"].rstrip(";").rstrip()
    if line[:m.start()].strip() or not expr or expr == NULL[ext] or not _balanced(expr):
        return None
    if expr.endswith(("\\", ",")) or re.search(r"(\band|\bor|[-+*/%&|=<>.?:])$", expr):
        return None  # continua na próxima linha
    return f"return {NULL[ext]}" + (";" if m["e"].rstrip().endswith(";") else "")


# Binário: operando antes, com o mesmo espaçamento dos dois lados (exclui *args, ponteiro, **).
def _binary(op: str) -> str:
    return rf"(?:(?<=[\w)\]] ){op}(?= )|(?<=[\w)\]]){op}(?=[\w(]))"


Rep = str | Callable[[re.Match, str, str], str | None]
# (nome, padrão, substituição, extensões; None = todas). Lookarounds evitam ->, =>, <<, ++, +=...
OPERATORS: list[tuple[str, re.Pattern, Rep, tuple[str, ...] | None]] = [
    (name, re.compile(pat), rep, langs) for name, pat, rep, langs in [
        ("==→!=", r"==(?!=)", "!=", None),
        ("!=→==", r"!=(?!=)", "==", None),
        ("<=→>", r"<=", ">", None),
        (">=→<", r"(?<![=>])>=", "<", None),
        ("<→>=", r"(?<![<=!-])<(?![<=-])", ">=", None),
        (">→<=", r"(?<![->=<])>(?![>=])", "<=", None),
        ("&&→||", r"&&", "||", None),
        ("||→&&", r"\|\|", "&&", None),
        ("and→or", r"\band\b", "or", None),
        ("or→and", r"\bor\b", "and", None),
        ("True→False", r"\bTrue\b", "False", None),
        ("False→True", r"\bFalse\b", "True", None),
        ("true→false", r"\btrue\b", "false", None),
        ("false→true", r"\bfalse\b", "true", None),
        # O e de 1e-5 é expoente; o de size+1 é identificador.
        ("+→-", r"(?<![+\d])(?<!\d[eE])\+(?![+=])", "-", None),
        ("-→+", r"(?<![-\d])(?<!\d[eE])-(?![->=])", "+", None),
        ("*→/", _binary(r"\*"), "/", None),
        ("/→*", _binary("/"), "*", None),
        ("%→*", _binary("%"), "*", None),
        ("not→∅", r"(?<!\bis )\bnot[ \t]+(?!in\b)", "", HASH[:1]),
        ("is not→is", r"\bis[ \t]+not\b", "is", HASH[:1]),
        ("is→is not", r"\bis\b(?![ \t]+not\b)", "is not", HASH[:1]),
        ("not in→in", r"\bnot[ \t]+in\b", "in", HASH[:1]),
        ("in→not in", r"(?<!\bnot )\bin\b", _not_for_in, HASH[:1]),
        ("!→∅", r"(?<![\w!)\]$])!(?![=!])", "", BANG),  # x!, macro!, !! e != ficam
        ("n→n+1", r"(?<![\w.$#])\d+(?![\w.])", _plus_one, None),
        ("return→nulo", r"(?<![\w.$])return[ \t]+(?P<e>\S.*?)[ \t]*$", _null_return, tuple(NULL)),
    ]
]
ANGLES = {"<→>=", ">→<="}


@dataclass
class Mutant:
    file: str
    line: int
    col: int
    operator: str
    original: str
    mutated: str
    status: str = "pending"  # killed | survived | timeout | invalid (build falhou: fora do score)

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
    def invalid(self) -> int:
        return sum(m.status == "invalid" for m in self.mutants)

    @property
    def score(self) -> float:
        scored = len(self.mutants) - self.invalid
        return self.killed / scored if scored else 1.0

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


def _code_region(line: str, markers: tuple[str, ...] = ("#", "//"), quotes: str = "\"'`") -> int:
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
        elif c in quotes:
            quote = c
        elif any(line.startswith(mk, i) for mk in markers):
            return i
        i += 1
    return len(line)


def _in_string(line: str, pos: int, quotes: str = "\"'`") -> bool:
    quote = None
    i = 0
    while i < pos:
        c = line[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in quotes:
            quote = c
        i += 1
    return quote is not None


_TYPE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_ ,.?:[]<>")


def _angle_skips(line: str, ext: str) -> set[int]:
    """Posições de < e > que delimitam tipo genérico ou tag JSX, não comparação."""
    skip: set[int] = set()
    if ext in GENERICS:
        for i, c in enumerate(line):
            # Map<K, V>, Vec::<u8>: o < cola no nome; o conteúdo só tem nomes, vírgulas e < >.
            if c != "<" or i == 0 or i in skip or not (line[i - 1].isalnum() or line[i - 1] in "_:"):
                continue
            depth = 0
            for j in range(i, len(line)):
                ch = line[j]
                if ch not in _TYPE_CHARS:
                    break
                depth += (ch == "<") - (ch == ">")
                if depth == 0:
                    skip.update(k for k in range(i, j + 1) if line[k] in "<>")
                    break
    if ext in JSX:
        i = 0
        while i < len(line):
            nxt = line[i + 1:i + 2]
            prev = line[i - 1] if i else " "
            if line[i] == "<" and (nxt in ("/", ">") or (nxt.isalpha() and not (prev.isalnum() or prev in "_)]"))):
                j, depth, quote = i + 1, 0, None
                while j < len(line):  # fecha no > fora de {expressão} e de atributo entre aspas
                    ch = line[j]
                    if quote:
                        quote = None if ch == quote else quote
                    elif ch in "\"'":
                        quote = ch
                    elif ch in "{}":
                        depth += 1 if ch == "{" else -1
                    elif ch == ">" and depth == 0:
                        break
                    j += 1
                skip.update(k for k in (i, j) if k < len(line))
                i = j
            i += 1
    return skip


def _compiles(text: str, rel: str) -> bool:
    try:
        compile(text, rel, "exec", dont_inherit=True)
    except (SyntaxError, ValueError):
        return False
    return True


def candidates(root: Path, files: list[str]) -> list[Mutant]:
    out: list[Mutant] = []
    for rel in files:
        try:
            lines = (root / rel).read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        ext = os.path.splitext(rel)[1]
        markers, starts, quotes = syntax(ext)
        python = ext == ".py"
        in_string = python_string_lines("\n".join(lines) + "\n") if python else set()
        # Mutante Python que não compila é descartado aqui: nunca conta como morto (AC-117).
        check = python and _compiles("\n".join(lines) + "\n", rel)
        for n, line in enumerate(lines, 1):
            s = line.strip()
            if n in in_string or not s or s.startswith(starts) or SKIP_MARK in line:
                continue
            if s.startswith(("import ", "from ", "#include", "package ", "using ")):
                continue
            end = _code_region(line, markers, quotes)
            angles = _angle_skips(line, ext)
            for name, pat, rep, langs in OPERATORS:
                if langs is not None and ext not in langs:
                    continue
                for m in pat.finditer(line, 0, end):
                    if _in_string(line, m.start(), quotes) or (name in ANGLES and m.start() in angles):
                        continue
                    new = rep if isinstance(rep, str) else rep(m, line, ext)
                    if new is None:
                        continue
                    mutated = line[:m.start()] + new + line[m.end():]
                    if check and not _compiles("\n".join(lines[:n - 1] + [mutated] + lines[n:]) + "\n", rel):
                        continue
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
        if any(not (work / m.file).resolve().is_relative_to(work.resolve()) for m in rep.mutants):
            rep.error = "alvo de mutação fora da cópia (symlink ou dependência compartilhada)"
            rep.mutants = []
            return rep
        env = {**os.environ, **{k: v.replace("{root}", str(work)) for k, v in cfg.env.items()}}
        private_tmp = work / ".sdd-tmp"
        private_tmp.mkdir()
        # Autotestes do sweep, inclusive mutados, só enxergam temporários desta cópia.
        env.update({key: str(private_tmp) for key in ("TMPDIR", "TEMP", "TMP")})
        # Bytecode em cache faria o Python rodar o código antigo quando a mutação não muda o
        # tamanho do arquivo (ex.: + → -) e ocorre no mesmo segundo: falso sobrevivente.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if cfg.build and _run(cfg.build, work, env, cfg.timeout) != "passed":
            rep.error = "o build não passa sem mutações; corrija mutation.build antes de medir"
            rep.mutants = []
            return rep
        if _run(cmd, work, env, cfg.timeout) != "passed":
            rep.error = "a suíte não passa sem mutações; corrija os testes antes de medir"
            rep.mutants = []
            return rep
        for m in rep.mutants:
            target = work / m.file
            if not target.resolve().is_relative_to(work.resolve()):
                rep.error = "alvo de mutação fora da cópia após execução dos testes"
                break
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
                # Não compilou: inválido, nem morto nem sobrevivente (AC-117).
                built = not cfg.build or _run(cfg.build, work, env, cfg.timeout) == "passed"
                result = _run(cmd, work, env, cfg.timeout) if built else "invalid"
            finally:
                try:
                    if not target.resolve().is_relative_to(work.resolve()):
                        raise OSError("restauração recusada: alvo fora da cópia")
                    _write(target, original, clock)
                except OSError:
                    rep.error = "cópia de trabalho indisponível; execução de mutação incompleta"
            m.status = {"failed": "killed", "passed": "survived", "timeout": "timeout",
                        "invalid": "invalid"}[result]
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
        scored = len(r.mutants) - r.invalid
        extra = f" {r.invalid} inválido(s) (não compilaram) ficaram fora do score." if r.invalid else ""
        out += ["", f"Score {r.score:.0%} (mínimo {r.min_score:.0%}): {r.killed}/{scored} "
                f"mutantes mortos, amostrados de {r.candidates} candidatos.{extra}", ""]
        surv = [m for m in r.mutants if m.status == "survived"]
        if surv:
            out += ["| Onde | Operador | Linha mutada |", "|---|---|---|"]
            out += [f"| `{m.where}` | {m.operator} | `{m.mutated.strip()}` |" for m in surv]
            out.append("")
        bad = [m for m in r.mutants if m.status == "invalid"]
        if bad:
            out += ["Inválidos (o build falhou; fora do score):", ""]
            out += [f"- `{m.where}` {m.operator}: `{m.mutated.strip()}`" for m in bad]
            out.append("")
    out += constitution_section(constitution)
    return "\n".join(out) + "\n"
