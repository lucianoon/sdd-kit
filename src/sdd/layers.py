"""Aplicação de camadas (`sdd enable`, presets do `sdd init`). Idempotente: nunca sobrescreve."""
from __future__ import annotations

import re
from pathlib import Path

from . import scaffold

CONFIG_PATH = "specs/sdd.yaml"
AGENTS_MD = "AGENTS.md"
WORKFLOW_PATH = ".github/workflows/sdd.yml"


def _write_new(root: Path, rel: str, content: str, actions: list[str]) -> None:
    p = root / rel
    if p.exists():
        actions.append(f"mantido  {rel}")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    actions.append(f"criado   {rel}")


def _config(root: Path, layer: str, actions: list[str]) -> None:
    snippet = scaffold.CONFIG_LAYERS.get(layer)
    if not snippet:
        return
    cfg = root / CONFIG_PATH
    if not cfg.exists():
        actions.append(f"ignorado {CONFIG_PATH} (ausente; rode `sdd init`)")
        return
    text = cfg.read_text(encoding="utf-8")
    keys = re.findall(r"^([a-z_]+):", snippet, re.MULTILINE)
    changed = False
    for key in keys:
        line = re.search(rf"^{key}:.*$", snippet, re.MULTILINE).group(0)
        current = re.search(rf"^{key}:.*$", text, re.MULTILINE)
        if current is None:
            continue
        if current.group(0).split("#")[0].strip() != line.split("#")[0].strip() and \
                line.split(":", 1)[1].strip() in ("true", "false"):
            text = text[:current.start()] + line + text[current.end():]  # liga a flag existente
            changed = True
    missing = [k for k in keys if not re.search(rf"^{k}:", text, re.MULTILINE)]
    if missing:
        text = text.rstrip("\n") + "\n" + snippet
        changed = True
    if changed:
        cfg.write_text(text, encoding="utf-8")
        actions.append(f"config   {CONFIG_PATH}: {', '.join(keys)}")
    else:
        actions.append(f"mantido  {CONFIG_PATH}: {', '.join(keys)} já configurado")


def _agents_md(root: Path, layer: str, actions: list[str]) -> None:
    section = scaffold.AGENTS_LAYERS.get(layer, "")
    if not section.strip():
        return
    p = root / AGENTS_MD
    text = p.read_text(encoding="utf-8") if p.exists() else scaffold.AGENTS_CORE
    if f"<!-- sdd:{layer} -->" in text:
        return
    p.write_text(text.rstrip("\n") + "\n" + section, encoding="utf-8")
    actions.append(f"seção    {AGENTS_MD}: {layer}")


def _workflow_mutate(root: Path, actions: list[str]) -> None:
    p = root / WORKFLOW_PATH
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    if "sdd mutate" in text or "      - if: always()" not in text:
        return
    p.write_text(text.replace("      - if: always()", scaffold.MUTATE_STEP + "      - if: always()", 1),
                 encoding="utf-8")
    actions.append(f"passo    {WORKFLOW_PATH}: sdd mutate nos PRs")


def apply_layer(root: Path, layer: str) -> list[str]:
    if layer not in scaffold.LAYERS:
        raise ValueError(f"camada '{layer}' não existe (disponíveis: {', '.join(scaffold.LAYERS)})")
    actions: list[str] = []
    if layer in scaffold.FILES_LAYERS:
        rel, content = scaffold.FILES_LAYERS[layer]
        _write_new(root, rel, content, actions)
    if layer == "agentes":
        from .profile import AGENTS_PATH, skeleton
        _write_new(root, AGENTS_PATH, skeleton("agentes"), actions)
    if layer == "mutate":
        _workflow_mutate(root, actions)
    _config(root, layer, actions)
    _agents_md(root, layer, actions)
    return actions


def init(root: Path, preset: str = "minimo", profile: str | None = None) -> list[str]:
    if preset not in scaffold.PRESETS:
        raise ValueError(f"preset '{preset}' não existe (disponíveis: {', '.join(scaffold.PRESETS)})")
    if profile not in (None, "agentes"):
        raise ValueError(f"perfil '{profile}' não existe (disponível: agentes)")
    actions: list[str] = []
    for rel, content in scaffold.initial_files(preset).items():
        _write_new(root, rel, content, actions)
    for layer in scaffold.PRESETS[preset] + (["agentes"] if profile else []):
        actions += [a for a in apply_layer(root, layer) if not a.startswith("mantido")]
    return actions
