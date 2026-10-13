"""Regras de arquitetura executáveis: quem pode importar quem.

Lê as linhas de import (Python, JS/TS, Go) dos arquivos sujeitos a cada regra e reprova
imports proibidos. Agnóstico de framework: não executa o código nem precisa de plugin.
Para outras linguagens, use ferramentas dedicadas (ArchUnit, dependency-cruiser,
import-linter) como `gates`.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from .diff import matches
from .textscan import python_string_lines

PY_EXT = (".py",)
JS_EXT = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
GO_EXT = (".go",)
SKIP_DIRS = {".git", ".sdd", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}

ALLOW = re.compile(r"sdd:\s*allow\s+(ARCH-\d{3,})\b[ \t]*(.*)")
PY_IMPORT = re.compile(r"^\s*import\s+(.+)$")
PY_FROM = re.compile(r"^\s*from\s+(\.*)([\w.]*)\s+import\b")
JS_PATTERNS = [
    re.compile(r"\bfrom\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"^\s*import\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    re.compile(r"\bimport\(\s*['\"]([^'\"]+)['\"]\s*\)"),
]
GO_SINGLE = re.compile(r"^\s*import\s+(?:[\w.]+\s+)?\"([^\"]+)\"")
GO_IN_BLOCK = re.compile(r"^\s*(?:[\w.]+\s+)?\"([^\"]+)\"")


@dataclass
class Import:
    line: int
    name: str  # como escrito: "openai", "@langchain/core", "./infra/db", "..infra"
    module: str  # nome normalizado para comparar com `forbid`
    path: str | None  # arquivo do repo alcançado (sem extensão), quando resolvível
    allow: tuple[str, str] | None  # (ARCH-id, motivo) de uma marcação sdd: allow


def _strip_ext(p: str) -> str:
    for ext in PY_EXT + JS_EXT + GO_EXT:
        if p.endswith(ext):
            return p[: -len(ext)]
    return p


def _python(rel: str, lines: list[str]) -> list[Import]:
    out = []
    pkg = rel.split("/")[:-1]
    in_string = python_string_lines("\n".join(lines) + "\n")
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if n in in_string or s.startswith("#"):
            continue
        allow = _allow(line)
        m = PY_FROM.match(line)
        if m:
            dots, name = m.group(1), m.group(2)
            if dots:  # import relativo: resolve para um caminho do repo
                base = pkg[: len(pkg) - (len(dots) - 1)] if len(dots) > 1 else pkg
                parts = base + (name.split(".") if name else [])
                path = "/".join(parts)
                out.append(Import(n, dots + name, ".".join(parts), path, allow))
            else:
                out.append(Import(n, name, name, None, allow))
            continue
        m = PY_IMPORT.match(line)
        if m:
            for chunk in m.group(1).split("#")[0].split(","):
                name = chunk.strip().split(" as ")[0].strip()
                if name:
                    out.append(Import(n, name, name, None, allow))
    return out


def _js(rel: str, lines: list[str]) -> list[Import]:
    out = []
    folder = posixpath.dirname(rel)
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith(("//", "*", "/*")):
            continue
        allow = _allow(line)
        seen = set()
        for pat in JS_PATTERNS:
            for name in pat.findall(line):
                if name in seen:
                    continue
                seen.add(name)
                path = None
                if name.startswith("."):
                    path = _strip_ext(posixpath.normpath(posixpath.join(folder, name)))
                out.append(Import(n, name, name, path, allow))
    return out


def _go(rel: str, lines: list[str]) -> list[Import]:
    out = []
    in_block = False
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("//"):
            continue
        if in_block:
            if s.startswith(")"):
                in_block = False
                continue
            m = GO_IN_BLOCK.match(line)
        elif re.match(r"^\s*import\s*\(", line):
            in_block = True
            continue
        else:
            m = GO_SINGLE.match(line)
        if m:
            out.append(Import(n, m.group(1), m.group(1), None, _allow(line)))
    return out


def _allow(line: str) -> tuple[str, str] | None:
    m = ALLOW.search(line)
    return (m.group(1), m.group(2).strip()) if m else None


def imports(root: Path, rel: str) -> list[Import]:
    try:
        lines = (root / rel).read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, FileNotFoundError):
        return []
    if rel.endswith(PY_EXT):
        return _python(rel, lines)
    if rel.endswith(JS_EXT):
        return _js(rel, lines)
    if rel.endswith(GO_EXT):
        return _go(rel, lines)
    return []


def module_matches(module: str, pattern: str) -> bool:
    """`openai` casa `openai`, `openai.types` e `openai/x`; aceita curingas (langchain*)."""
    return (fnmatchcase(module, pattern) or module.startswith(pattern + ".")
            or module.startswith(pattern + "/"))


def source_files(root: Path) -> list[str]:
    exts = PY_EXT + JS_EXT + GO_EXT
    out = []
    for p in root.rglob("*"):
        if p.is_file() and p.name.endswith(exts):
            rel = p.relative_to(root).as_posix()
            if not SKIP_DIRS.intersection(rel.split("/")[:-1]):
                out.append(rel)
    return sorted(out)


def check(proj) -> dict:
    report = {"ok": True, "rules": [r.id for r in proj.arch], "files": 0,
              "violations": [], "exceptions": [], "problems": []}
    if not proj.arch:
        return report
    files = source_files(proj.root)
    checked: set[str] = set()
    for rule in proj.arch:
        targets = [f for f in files if matches(f, rule.sources)]
        if not targets:
            report["problems"].append(
                f"{rule.id}: nenhum arquivo casa {rule.sources} (glob errado? a regra não protege nada)")
            continue
        checked.update(targets)
        for rel in targets:
            for imp in imports(proj.root, rel):
                hit = next((p for p in rule.forbid if module_matches(imp.module, p)), None)
                if hit is None and imp.path is not None:
                    hit = next((p for p in rule.forbid_paths
                                if matches(imp.path, [p]) or matches(imp.path + "/x", [p])), None)
                if hit is None:
                    continue
                entry = {"rule": rule.id, "file": rel, "line": imp.line, "import": imp.name,
                         "matched": hit}
                if imp.allow and imp.allow[0] == rule.id and imp.allow[1]:
                    report["exceptions"].append({**entry, "reason": imp.allow[1]})
                else:
                    if imp.allow and imp.allow[0] == rule.id:
                        entry["detail"] = "marcação sdd: allow sem motivo não vale"
                    report["violations"].append(entry)
    report["files"] = len(checked)
    report["ok"] = not report["violations"] and not report["problems"]
    return report
