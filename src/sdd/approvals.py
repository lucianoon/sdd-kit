"""Aprovação humana ligada ao conteúdo aprovado (AD-008). Declaração, nunca evidência.

A spec aprovada é tudo exceto design, tarefas e aprovações; o plano é design e tarefas.
O hash vem do documento validado, não do texto: reformatar ou comentar não invalida, e
status e evidence de tarefas mudam ao implementar sem pedir nova aprovação.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re

import yaml
from pydantic import ValidationError

from .artifacts import UniqueLoader, atomic_write
from .models import Approval, Spec

STAGES = ("spec", "plan")
TASK_FIELDS = {"id", "title", "origin", "depends_on", "done_when"}
_TOP_LEVEL = re.compile(r"^[^\s-]", re.MULTILINE)


class ApprovalError(ValueError):
    pass


def digest(spec: Spec, stage: str) -> str:
    if stage == "spec":
        data = spec.model_dump(mode="json", exclude_defaults=True, exclude={"approvals", "design", "tasks"})
    else:
        data = {"design": spec.design.model_dump(mode="json", exclude_defaults=True) if spec.design else None,
                "tasks": [t.model_dump(mode="json", exclude_defaults=True, include=TASK_FIELDS) for t in spec.tasks]}
    text = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def required(spec: Spec, config) -> dict[str, bool]:
    on = bool(config and config.require_approval and spec.size in config.approval_required_for)
    return {"spec": on, "plan": on and bool(spec.design or spec.tasks)}


def states(spec: Spec, config) -> list[dict]:
    need = required(spec, config)
    out = []
    for stage in STAGES:
        rec = next((a for a in spec.approvals if a.stage == stage), None)
        if rec is None:
            state = "AUSENTE"
        else:
            state = "APROVADO" if rec.digest == digest(spec, stage) else "DESATUALIZADO"
        out.append({"stage": stage, "state": state, "required": need[stage],
                    "by": rec.by if rec else None, "date": rec.date.isoformat() if rec else None,
                    "quote": rec.quote if rec else None})
    return out


def waiting(spec: Spec, config) -> list[dict]:
    """Etapas exigidas sem aprovação atual: bloqueiam a implementação."""
    return [s for s in states(spec, config) if s["required"] and s["state"] != "APROVADO"]


def problems(rel: str, spec: Spec, config) -> list[str]:
    out = []
    for s in states(spec, config):
        if s["state"] == "DESATUALIZADO":
            out.append(f"{rel}: aprovação de {s['stage']} DESATUALIZADA: o conteúdo mudou depois de "
                       f"{s['date']}; peça nova aprovação e registre com `sdd approve`")
        elif s["required"] and s["state"] == "AUSENTE":
            out.append(f"{rel}: aprovação de {s['stage']} AUSENTE (require_approval); apresente a etapa "
                       "ao usuário e registre as palavras dele com `sdd approve`")
    return out


def _closure(proj, rel: str, spec: Spec) -> list[str]:
    """O que impede apresentar a spec: pergunta sem resposta e campo ainda a preencher."""
    from .project import PLACEHOLDER

    out = [f"pergunta aberta sem resposta: {q.question}" for q in spec.open_questions if not q.answer.strip()]
    return out + [e for e in proj.errors if e.startswith(f"{rel}:") and f"{PLACEHOLDER}:" in e]


def _with_approval(text: str, spec: Spec, approval: Approval) -> str:
    items = sorted([a for a in spec.approvals if a.stage != approval.stage] + [approval],
                   key=lambda a: STAGES.index(a.stage))
    block = "approvals:\n" + yaml.safe_dump([a.model_dump() for a in items], allow_unicode=True,
                                            sort_keys=False, width=1_000_000)
    current = re.search(r"^approvals:.*$", text, re.MULTILINE)
    if current is None:
        return text.rstrip("\n") + "\n" + block
    nxt = _TOP_LEVEL.search(text, current.end() + 1)
    return text[:current.start()] + block + text[nxt.start() if nxt else len(text):]


def approve(proj, feature: str, stage: str, by: str, quote: str,
            today: datetime.date | None = None) -> tuple[str, Approval]:
    if stage not in STAGES:
        raise ApprovalError(f"etapa '{stage}' inválida (disponíveis: {', '.join(STAGES)})")
    by, quote = by.strip(), quote.strip()
    if not by or not quote:
        raise ApprovalError("informe --by e --quote com as palavras de quem aprovou; "
                            "aprovação sem palavras não é registrada")
    matches = [(p, s) for p, s in proj.specs.items() if s.feature == feature]
    if len(matches) != 1:
        raise ApprovalError(f"feature '{feature}' " + ("ambígua" if matches else "não encontrada ou spec inválida"))
    rel, spec = matches[0]
    blocking = _closure(proj, rel, spec)
    if stage == "plan":
        if not spec.design and not spec.tasks:
            blocking.append("o plano não tem design nem tarefas")
        if next(s for s in states(spec, proj.config) if s["stage"] == "spec")["state"] != "APROVADO":
            blocking.append("a spec não tem aprovação atual; aprove a spec antes do plano")
        blocking += [e for e in proj.errors if (e.startswith(f"{rel}:") or not e.startswith("specs/features/"))
                     and e not in blocking]
    if blocking:
        raise ApprovalError(f"{rel}: corrija antes de aprovar {stage}: " + "; ".join(blocking))
    approval = Approval(stage=stage, by=by, date=today or datetime.date.today(), quote=quote,
                        digest=digest(spec, stage))
    path = proj.root / rel
    text = _with_approval(path.read_text(encoding="utf-8"), spec, approval)
    # Confere em memória antes de gravar: a spec continua válida e só approvals mudou.
    try:
        updated = Spec.model_validate(yaml.load(text, Loader=UniqueLoader))
    except (ValidationError, yaml.YAMLError) as exc:
        raise ApprovalError(f"{rel}: a aprovação não pôde ser registrada sem alterar a spec: {exc}") from exc
    if updated.model_dump(exclude={"approvals"}) != spec.model_dump(exclude={"approvals"}):
        raise ApprovalError(f"{rel}: a aprovação não pôde ser registrada sem alterar a spec")
    atomic_write(proj.root, rel, text)
    return rel, approval
