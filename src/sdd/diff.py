"""Detecção de divergência por mudança: código e spec precisam andar juntos.

A comparação da spec é semântica: comentários, espaços e reordenação de chaves não
contam como mudança. Assim, tocar a spec de forma cosmética não libera código alterado.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .core import Project

GIT_TIMEOUT = 60  # segundos
TRAILER = re.compile(r"^SDD-No-Spec-Change:[ \t]*(.+)$", re.MULTILINE)
# Correção de bug: o código descumpria uma spec correta. Não exige mudar a spec, exige um
# teste de regressão alterado no mesmo PR que cite o critério corrigido.
FIX_TRAILER = re.compile(r"^SDD-Fix:[ \t]*(.+)$", re.MULTILINE)
CRITERION = re.compile(r"\b(?:AC|NFR)-\d{3,}\b")


class GitError(RuntimeError):
    pass


@lru_cache(maxsize=None)
def _glob_regex(pattern: str) -> re.Pattern:
    """Glob estilo gitignore: ** cruza diretórios, * não."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(f"^{out}$")


def matches(path: str, patterns: list[str]) -> bool:
    return any(_glob_regex(p).match(path) for p in patterns)


def _git(root: Path, *args: str) -> str:
    try:
        # encoding já liga o modo texto
        p = subprocess.run(["git", *args], cwd=root, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {' '.join(args)}: excedeu {GIT_TIMEOUT}s")
    if p.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def changes(root: Path, base: str) -> tuple[list[str], str, str]:
    """Arquivos alterados desde o merge-base com `base` (inclui não commitados e
    não rastreados), as mensagens de commit do intervalo e o merge-base."""
    mb = _git(root, "merge-base", base, "HEAD").strip()
    files = set(_git(root, "diff", "--name-only", mb).split())
    files |= set(_git(root, "ls-files", "--others", "--exclude-standard").split())
    messages = _git(root, "log", "--format=%B", f"{mb}..HEAD")
    return sorted(files), messages, mb


def semantic_hash(text: str) -> str:
    """Hash do conteúdo da spec sem ruído: sem comentários e espaço irrelevante.

    Comment-only defuses: uma edição que só acrescenta comentário (ou reordena chaves,
    muda aspas ou espaçamento) produz o mesmo hash e não libera o diff.

    Comentários de linha (`#`) e de bloco são removidos antes do parse — YAML não os
    preserva de todo jeito; remover antes evia falsa diferença por formatação.
    """
    body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    try:
        data = yaml.safe_load(body) or {}
    except yaml.YAMLError:
        return repr(("ilegível", body.strip()))  # YAML quebrado: compara como texto cru
    return repr(_canon(data))


def _canon(obj):
    """Representação canônica: dicts ordenados por chave, listas preservam a ordem
    (lista tem semântica posicional: reordenar critérios muda o documento)."""
    if isinstance(obj, dict):
        return {k: _canon(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_canon(v) for v in obj]
    return obj


@dataclass
class DiffResult:
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    override: str | None = None
    changed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def _regression_tests(proj: Project, changed: list[str], ids: set[str]) -> dict[str, list[str]]:
    """Para cada ID, os arquivos de teste alterados no PR que o citam."""
    from .core import ID_IN_TEST

    test_globs = proj.config.tests.paths if proj.config else []
    found: dict[str, list[str]] = {i: [] for i in ids}
    for f in changed:
        if not matches(f, test_globs):
            continue
        try:
            text = (proj.root / f).read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError, IsADirectoryError):
            continue
        cited = {f"{(m['a'] or m['b']).upper()}-{m['n']}" for m in ID_IN_TEST.finditer(text)}
        for i in ids & cited:
            found[i].append(f)
    return found


def _git_show(root: Path, ref: str, path: str) -> str | None:
    """Conteúdo de um arquivo num commit; None se não existe."""
    try:
        return _git(root, "show", f"{ref}:{path}")
    except GitError:
        return None


def _meaningful_spec_change(root: Path, rel: str, base: str) -> bool:
    """A spec mudou *de verdade*? Compara o conteúdo parseado com a versão na base.

    Comentário, espaço e ordem de chaves não contam; qualquer valor de conteúdo sim.
    O `base` já é o merge-base calculado pelo `changes`.
    """
    try:
        old = _git_show(root, base, rel)
    except GitError:
        return True  # arquivo novo (não existe na base) ou git indisponível: conserva
    try:
        new = (root / rel).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return True
    if old is None:
        return True  # spec nova: a mudança é real
    return semantic_hash(old) != semantic_hash(new)


def evaluate(proj: Project, changed: list[str], messages: str, merge_base: str = "HEAD") -> DiffResult:
    res = DiffResult(changed=changed)
    m = TRAILER.search(messages)
    res.override = m.group(1).strip() if m else None
    code_globs = proj.config.code if proj.config else []
    found: list[str] = []
    fix_ids = {i for line in FIX_TRAILER.findall(messages) for i in CRITERION.findall(line)}
    known = {c[0] for s in proj.specs.values() for c in s.criteria()}
    for i in sorted(fix_ids - known):
        res.violations.append(f"SDD-Fix cita {i}, que não existe em nenhuma spec")
    regression = _regression_tests(proj, changed, fix_ids & known)

    owned: set[str] = set()
    for rel, spec in proj.specs.items():
        spec_dir = rel.rsplit("/", 1)[0] + "/"
        touched = any(f.startswith(spec_dir) for f in changed)
        # Mudança cosmética na spec (só comentário/espaço/ordem de chave) não libera código.
        spec_changed = touched and _meaningful_spec_change(proj.root, rel, merge_base)
        code = [f for f in changed if spec.paths and matches(f, spec.paths)]
        owned.update(code)
        limit = proj.config.small_max_files if proj.config else 3
        if spec.size == "small" and len(code) > limit:
            # Não é liberado pelo trailer: reclassificar o tamanho é uma mudança de spec legítima.
            res.violations.append(
                f"{spec.feature}: marcada como small mas alterou {len(code)} arquivos de código "
                f"(limite {limit}); reclassifique o size ou divida a mudança")
        mine = {c[0] for c in spec.criteria()} & fix_ids
        if code and not spec_changed and mine:
            missing = sorted(i for i in mine if not regression[i])
            if missing:
                res.violations.append(
                    f"{spec.feature}: SDD-Fix cita {', '.join(missing)} sem teste de regressão alterado "
                    "que cite o ID (correção sem teste não comprova nada)")
            for i in sorted(mine - set(missing)):
                res.warnings.append(f"{spec.feature}: correção de {i} sem mudar a spec, com teste de "
                                    f"regressão em {', '.join(regression[i])}")
        elif code and not spec_changed:
            found.append(
                f"{spec.feature}: código alterado sem mudança em {spec_dir} "
                f"({', '.join(code[:3])}{' …' if len(code) > 3 else ''})"
            )
        elif spec_changed and not code and spec.paths:
            res.warnings.append(f"{spec.feature}: spec alterada sem código (ok se a implementação vem depois)")
        # Dataset de eval é a régua: mudar a régua sem mudar a spec seria afrouxar o teste em silêncio.
        datasets = [e.dataset for e in spec.evals if e.dataset in changed]
        if datasets and not spec_changed:
            found.append(f"{spec.feature}: dataset de eval alterado sem mudança em {spec_dir} "
                         f"({', '.join(datasets)})")

    for f in changed:
        if code_globs and matches(f, code_globs) and f not in owned:
            found.append(f"{f}: código sem feature dona (declare em `paths` de alguma spec)")

    if res.override:
        res.warnings += [f"liberado por SDD-No-Spec-Change: {v}" for v in found]
    else:
        res.violations += found
    return res
