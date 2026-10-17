"""Conservative Markdown import: drafts with provenance, never silent approval."""
from __future__ import annotations

import re
from pathlib import Path

from .artifacts import ArtifactError, atomic_write, confined
from .learning import digest, save, slug
from .specify import _existing


FIELDS = re.compile(r"\*\*(GIVEN|WHEN|THEN|AND)\*\*\s*[: ,.-]?\s*", re.I)


def parse(text: str, kind: str) -> tuple[list[dict], list[str]]:
    if kind not in ("speckit", "openspec"):
        raise ArtifactError("formato precisa ser speckit ou openspec")
    requirements, warnings = [], []
    active, scenario, last = None, None, None
    fenced = False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
        if fenced:
            continue
        heading = (re.match(r"^###\s+Requirement:\s*(.+)", line, re.I) if kind == "openspec"
                   else re.match(r"^###\s+User Story\s+(.+)", line, re.I))
        if heading:
            active = {"description": heading[1].strip(), "acceptance": []}
            requirements.append(active)
            scenario, last = None, None
            continue
        if kind == "openspec" and re.match(r"^####\s+Scenario:", line, re.I):
            if active is None:
                warnings.append("cenário fora de requisito; revise a fonte")
                continue
            scenario = {"given": "PREENCHER: estado inicial do cenário", "when": "", "then": ""}
            active["acceptance"].append(scenario)
            last = None
        matches = list(FIELDS.finditer(line))
        if not matches:
            continue
        if active is None:
            warnings.append("critério fora de requisito reconhecido; revise a fonte")
            continue
        if scenario is None or (kind == "speckit" and matches[0][1].lower() == "given"):
            scenario = {"given": "", "when": "", "then": ""}
            active["acceptance"].append(scenario)
            last = None
        for i, m in enumerate(matches):
            field = m[1].lower()
            value = line[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(line)].strip(" ,")
            if field == "and":
                if last:
                    scenario[last] += "; " + value
                else:
                    warnings.append("AND sem contexto; revise a fonte")
            else:
                scenario[field] = value
                last = field
    for req in requirements:
        if not req["acceptance"]:
            req["acceptance"].append({"given": "", "when": "", "then": ""})
        for ac in req["acceptance"]:
            for field in ("given", "when", "then"):
                if not ac[field]:
                    ac[field] = f"PREENCHER: {field} não reconhecido na fonte"
    if not requirements:
        raise ArtifactError("nenhum requisito reconhecido; fonte preservada, nenhuma spec criada")
    warnings.append("Importação parcial: prosa, tarefas, deltas ADDED/MODIFIED/REMOVED e NFRs exigem revisão manual.")
    return requirements, warnings


def import_spec(root: Path, source: str, kind: str, feature: str):
    slug(feature)
    origin = confined(root, source)
    text = origin.read_text(encoding="utf-8")
    requirements, warnings = parse(text, kind)
    top, existing, _ = _existing(root)
    if feature in existing:
        raise ArtifactError("feature já existe; use uma proposta de mudança")
    prefix = f"specs/imports/{feature}"
    outputs = [prefix + "/spec.yaml", prefix + "/source.md", prefix + "/import.yaml"]
    for path in outputs:
        if confined(root, path).exists():
            raise ArtifactError("importação existente preservada")
    next_ac = top["AC"]
    for i, req in enumerate(requirements, top["REQ"] + 1):
        req["id"] = f"REQ-{i:03d}"
        for ac in req["acceptance"]:
            next_ac += 1
            ac["id"] = f"AC-{next_ac:03d}"
    spec = {"feature": feature, "version": 1, "size": "medium",
            "summary": "PREENCHER: revisar a importação antes de promover para specs/features",
            "requirements": requirements, "paths": [], "out_of_scope": []}
    meta = {"version": 1, "format": kind, "source": source, "sha256": digest(origin),
            "status": "draft", "warnings": warnings, "verification": "NÃO_EXECUTADA",
            "id_policy": "IDs novos; imports concorrentes devem ser reconciliados antes da promoção"}
    atomic_write(root, outputs[1], text)
    save(root, outputs[0], spec)
    save(root, outputs[2], meta)
    return {**meta, "draft": outputs[0]}
