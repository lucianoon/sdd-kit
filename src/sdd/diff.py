"""Detecção de divergência por mudança: código e spec precisam andar juntos."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .core import Project

TRAILER = re.compile(r"^SDD-No-Spec-Change:[ \t]*(.+)$", re.MULTILINE)


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
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if p.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def changes(root: Path, base: str) -> tuple[list[str], str]:
    """Arquivos alterados desde o merge-base com `base` (inclui não commitados e
    não rastreados) e as mensagens de commit do intervalo."""
    mb = _git(root, "merge-base", base, "HEAD").strip()
    files = set(_git(root, "diff", "--name-only", mb).split())
    files |= set(_git(root, "ls-files", "--others", "--exclude-standard").split())
    messages = _git(root, "log", "--format=%B", f"{mb}..HEAD")
    return sorted(files), messages


@dataclass
class DiffResult:
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    override: str | None = None
    changed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def evaluate(proj: Project, changed: list[str], messages: str) -> DiffResult:
    res = DiffResult(changed=changed)
    m = TRAILER.search(messages)
    res.override = m.group(1).strip() if m else None
    code_globs = proj.config.code if proj.config else []
    found: list[str] = []

    owned: set[str] = set()
    for rel, spec in proj.specs.items():
        spec_dir = rel.rsplit("/", 1)[0] + "/"
        spec_changed = any(f.startswith(spec_dir) for f in changed)
        code = [f for f in changed if spec.paths and matches(f, spec.paths)]
        owned.update(code)
        limit = proj.config.small_max_files if proj.config else 3
        if spec.size == "small" and len(code) > limit:
            # Não é liberado pelo trailer: reclassificar o tamanho é uma mudança de spec legítima.
            res.violations.append(
                f"{spec.feature}: marcada como small mas alterou {len(code)} arquivos de código "
                f"(limite {limit}); reclassifique o size ou divida a mudança")
        if code and not spec_changed:
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
