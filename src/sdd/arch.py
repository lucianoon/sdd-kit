"""Regras de arquitetura executáveis: quem pode importar quem.

Lê as linhas de import (Python, JS/TS, Go) dos arquivos sujeitos a cada regra e reprova
imports proibidos. Agnóstico de framework: não executa o código nem precisa de plugin.
Para outras linguagens, use ferramentas dedicadas (ArchUnit, dependency-cruiser,
import-linter) como `gates`.
"""
from __future__ import annotations

import ast
import os
import posixpath
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from .diff import matches

PY_EXT = (".py",)
JS_EXT = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
GO_EXT = (".go",)
SKIP_DIRS = {".git", ".sdd", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}

ALLOW = re.compile(r"sdd:\s*allow\s+(ARCH-\d{3,})\b[ \t]*(.*)")
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


def _python(rel: str, lines: list[str], modules: dict[str, str]) -> list[Import]:
    out = []
    pkg = rel.split("/")[:-1]
    tree = ast.parse("\n".join(lines), filename=rel)
    nodes = sorted((n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))),
                   key=lambda n: (n.lineno, n.col_offset))
    for node in nodes:
        n = node.lineno
        allow = _allow(lines[n - 1])
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(Import(n, alias.name, alias.name, modules.get(alias.name), allow))
        else:
            name = node.module or ""
            dots = "." * node.level
            if node.level:
                base = pkg[:len(pkg) - node.level + 1]
                path = "/".join(base + (name.split(".") if name else []))
                module = path.replace("/", ".")
            else:
                path, module = modules.get(name), name
            if name:
                out.append(Import(n, dots + name, module, path, allow))
            for alias in node.names:
                child = (path + "/" + alias.name) if path else modules.get(name + "." + alias.name)
                if alias.name != "*" and (not name or child in modules.values()):
                    out.append(Import(n, dots + name + ("." if name else "") + alias.name,
                                      module + "." + alias.name, child, allow))
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


def imports(root: Path, rel: str, modules: dict[str, str] | None = None) -> list[Import]:
    lines = (root / rel).read_text(encoding="utf-8").splitlines()
    if rel.endswith(PY_EXT):
        return _python(rel, lines, modules or {})
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
    for directory, folders, names in os.walk(root):
        folders[:] = sorted(n for n in folders if n not in SKIP_DIRS)
        for name in names:
            p = Path(directory) / name
            if p.is_file() and name.endswith(exts):
                out.append(p.relative_to(root).as_posix())
    return sorted(out)


def check(proj) -> dict:
    from .report import metadata

    report = {**metadata("arch"), "ok": True, "rules": [r.id for r in proj.arch], "files": 0,
              "violations": [], "exceptions": [], "problems": []}
    if not proj.arch:
        return report
    files = source_files(proj.root)
    modules = {}
    for file in files:
        if file.endswith(".py"):
            stem = file[:-3]
            if stem.endswith("/__init__"):
                stem = stem[:-9]
            modules[stem.replace("/", ".")] = stem
            if stem.startswith("src/"):
                modules[stem[4:].replace("/", ".")] = stem
    report["rule_results"] = {}
    checked: set[str] = set()
    for rule in proj.arch:
        start_problems = len(report["problems"])
        start_violations = len(report["violations"])
        targets = [f for f in files if matches(f, rule.sources)]
        if not targets:
            report["problems"].append(
                f"{rule.id}: nenhum arquivo casa {rule.sources} (glob errado? a regra não protege nada)")
        checked.update(targets)
        for rel in targets:
            try:
                observed = imports(proj.root, rel, modules)
            except (OSError, UnicodeError, SyntaxError) as exc:
                report["problems"].append(f"{rule.id}: {rel}: não foi possível analisar: {exc}")
                continue
            for imp in observed:
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
        report["rule_results"][rule.id] = ("OK" if len(report["problems"]) == start_problems
                                          and len(report["violations"]) == start_violations else "FALHOU")
    report["files"] = len(checked)
    report["ok"] = not report["violations"] and not report["problems"]
    return report


def render_markdown(report: dict) -> str:
    from .report import version_line, constitution_section

    out = ["# Relatório de arquitetura SDD", "", version_line(report), "",
           f"**Resultado: {'APROVADO' if report['ok'] else 'REPROVADO'}**", "",
           f"{len(report['rules'])} regra(s), {report['files']} arquivo(s) verificado(s)."]
    out += [f"- {v['rule']}: `{v['file']}:{v['line']}` importa `{v['import']}`" for v in report['violations']]
    out += [f"- {p}" for p in report['problems']]
    out += [f"- Exceção {e['rule']}: `{e['file']}:{e['line']}` — {e['reason']}" for e in report['exceptions']]
    out += constitution_section(report.get("constitution"))
    return "\n".join(out) + "\n"
