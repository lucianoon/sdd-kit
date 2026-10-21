"""Revisão escalonada por risco (AD-007): piso determinístico, achados de LLM como
evidência probabilística e correções exportadas como casos de avaliação.

Nada aqui chama modelo. Entradas externas (classificador, revisor LLM) chegam como
arquivos e só podem elevar o rigor; aprovação de agente nunca conta como humana.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from .artifacts import ArtifactError, confined, parse_json
from .diff import CRITERION, FIX_TRAILER, GitError, _git, matches
from .models import TIERS, ProjectPath, ReviewConfig, Strict, Tier
from .project import CONFIG_PATH, Project
from .report import metadata, version_line

SEVERITY_TIER = {"low": "low", "medium": "medium", "high": "high"}


def rank(tier: str) -> int:
    return TIERS.index(tier)


def higher(a: str, b: str) -> str:
    return a if rank(a) >= rank(b) else b


def _config(proj: Project) -> ReviewConfig:
    if proj.config is None:
        raise ArtifactError(f"{CONFIG_PATH}: config ausente ou inválida")
    return proj.config.review


def _read_json(root: Path, rel: str, model):
    """None se o arquivo não existe; ArtifactError se existe e é inválido."""
    path = confined(root, rel)
    if not path.exists():
        return None
    try:
        return model.model_validate(parse_json(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError, ValidationError, RecursionError) as exc:
        raise ArtifactError(f"{rel}: {exc}") from exc


# --- Piso de risco -----------------------------------------------------------------

class Escalation(Strict):
    tier: Tier
    reason: str = Field(min_length=1)
    source: str = Field(min_length=1)  # quem pediu: classificador, revisor, pessoa


class Escalations(Strict):
    version: Literal[1] = 1
    escalations: list[Escalation] = []


def file_tier(proj: Project, cfg: ReviewConfig, path: str) -> tuple[str, list[str]]:
    """Tier de um arquivo alterado e os motivos. Só regras declaradas, sem inferência."""
    matched = [t for t in TIERS if matches(path, cfg.tiers.get(t, []))]
    if matched:
        tier = max(matched, key=rank)
        reasons = [f"review.tiers.{tier}"]
    else:
        tier, reasons = cfg.default_tier, [f"review.default_tier ({cfg.default_tier})"]
    if path == CONFIG_PATH:
        tier = "high"
        reasons.append(f"{CONFIG_PATH} define gates e o próprio piso: high")
    elif path.startswith("specs/") and rank(tier) < rank("medium"):
        tier = "medium"
        reasons.append("contrato do projeto (specs/): mínimo medium")
    for rel, spec in sorted(proj.specs.items()):
        owned = bool(spec.paths) and matches(path, spec.paths)
        if not (owned or path.startswith(rel.rsplit("/", 1)[0] + "/")) or not spec.design:
            continue
        for risk in spec.design.risks:
            risk_tier = SEVERITY_TIER[risk.severity]
            if rank(risk_tier) > rank(tier):
                tier = risk_tier
                reasons.append(f"{spec.feature}: risco {risk.severity} ({risk.area})")
    return tier, reasons


def risk(proj: Project, changed: list[str], author: str | None = None,
         approvals: int | None = None) -> dict:
    cfg = _config(proj)
    files = []
    # .sdd/ guarda relatórios e entradas do próprio kit, não código da mudança.
    for path in sorted(p for p in set(changed) if not p.startswith(".sdd/")):
        tier, reasons = file_tier(proj, cfg, path)
        files.append({"path": path, "tier": tier, "reasons": reasons})
    floor = "low"
    for f in files:
        floor = higher(f["tier"], floor)
    notes = [] if files else ["nenhum arquivo alterado"]
    tier = floor
    applied, ignored = [], []
    doc = _read_json(proj.root, cfg.escalations, Escalations)
    for esc in (doc.escalations if doc else []):
        if rank(esc.tier) > rank(tier):
            tier = esc.tier
            applied.append(esc.model_dump())
        else:
            ignored.append({**esc.model_dump(), "why": "não eleva o tier atual; escalação nunca reduz o piso"})
    required = cfg.approvals[tier]
    trusted = None
    if cfg.trusted_authors:
        trusted = author is not None and author in cfg.trusted_authors
        if not trusted and required < 1:
            required = 1
            notes.append("autor fora de trusted_authors (ou não informado): mínimo de 1 aprovação humana")
    ok = approvals is None or approvals >= required
    return {**metadata("risk"), "ok": ok, "status": "INFORMATIVO" if approvals is None else (
                "APROVADO" if ok else "REPROVADO"),
            "tier": tier, "floor": floor, "required_approvals": required, "approvals": approvals,
            "author": author, "trusted": trusted, "files": files,
            "escalations": {"applied": applied, "ignored": ignored}, "notes": notes,
            "scope": "piso por regras declaradas; escalações só elevam. Informe em --approvals apenas "
                     "aprovações de pessoas: aprovação de agente não conta"}


def render_risk(report: dict) -> str:
    out = ["# Piso de risco da mudança", "", version_line(report), "",
           f"**Tier: {report['tier']}** (piso {report['floor']}) · aprovações humanas exigidas: "
           f"{report['required_approvals']} · estado: {report['status']}", "",
           report["scope"] + ".", "", "| Arquivo | Tier | Motivos |", "|---|---|---|"]
    out += [f"| {f['path']} | {f['tier']} | {'; '.join(f['reasons'])} |" for f in report["files"]]
    for title, key in (("Escalações aplicadas", "applied"), ("Escalações ignoradas", "ignored")):
        if report["escalations"][key]:
            out += ["", f"## {title}", ""] + [
                f"- {e['tier']} por {e['source']}: {e['reason']}" + (f" ({e['why']})" if "why" in e else "")
                for e in report["escalations"][key]]
    if report["notes"]:
        out += ["", "## Notas", ""] + [f"- {n}" for n in report["notes"]]
    return "\n".join(out) + "\n"


# --- Achados de revisor LLM ----------------------------------------------------------

class Finding(Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    severity: Literal["important", "nit", "pre_existing"]
    path: ProjectPath
    line: int = Field(ge=1)
    category: str = ""  # classe do problema: corrigir todas as ocorrências, não uma linha
    message: str = Field(min_length=1)
    votes: int = Field(ge=0)  # verificadores que confirmaram
    voters: int = Field(ge=1)  # verificadores consultados
    round: int = Field(ge=1)  # rodada em que o achado surgiu
    status: Literal["open", "fixed", "dismissed"] = "open"
    # Destino de um achado descartado: mede o ruído do revisor.
    disposition: Literal["", "wrong", "intentional", "irrelevant"] = ""
    reason: str = ""

    @model_validator(mode="after")
    def _coerencia(self):
        if self.votes > self.voters:
            raise ValueError("votes maior que voters")
        if self.status == "dismissed" and (not self.disposition or not self.reason.strip()):
            raise ValueError("achado descartado precisa de disposition e reason")
        if self.status != "dismissed" and self.disposition:
            raise ValueError("disposition só vale para achado descartado")
        return self


class FindingsDoc(Strict):
    version: Literal[1] = 1
    reviewer: str = Field(min_length=1)  # harness e modelo que revisaram
    round: int = Field(ge=1)  # rodada atual do ciclo revisão/correção
    reviewed: dict[ProjectPath, str] = Field(min_length=1)  # arquivo -> sha256 revisado
    findings: list[Finding] = []


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _signature(f: Finding) -> tuple[str, str]:
    return f.path, " ".join(f.message.casefold().split())


def findings(proj: Project) -> dict:
    cfg = _config(proj)
    base = {**metadata("findings"), "evidence": "probabilística", "counts_as_human_approval": False,
            "scope": "integridade e bloqueios declarados por um revisor LLM externo; não executa o "
                     "revisor, não substitui testes e não conta como aprovação humana"}
    doc = _read_json(proj.root, cfg.findings, FindingsDoc)
    if doc is None:
        return {**base, "ok": True, "state": "AUSENTE", "problems": [], "blocking": [],
                "stale": [], "summary": {}, "source": cfg.findings}
    problems, stale = [], []
    if not cfg.allow_llm_findings:
        problems.append("achados de revisor LLM exigem review.allow_llm_findings: true (AD-007)")
    for rel, sha in sorted(doc.reviewed.items()):
        target = confined(proj.root, rel)
        if not target.is_file() or _sha(target) != sha:
            stale.append(rel)
    if stale:
        problems.append("revisão desatualizada: arquivos mudaram depois da revisão; repita a rodada")
    ids = [f.id for f in doc.findings]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"ID de achado repetido: {dup}")
    seen: dict[tuple[str, str], str] = {}
    for f in doc.findings:
        key = _signature(f)
        if key in seen and seen[key] != f.id:
            problems.append(f"{f.id}: repete o achado {seen[key]} (mesmo arquivo e mensagem)")
        seen.setdefault(key, f.id)
        if f.round > doc.round:
            problems.append(f"{f.id}: rodada {f.round} posterior à rodada atual {doc.round}")
    if doc.round > cfg.max_rounds:
        problems.append(f"rodada {doc.round} excede review.max_rounds={cfg.max_rounds}: "
                        "reveja a abordagem em vez de mais uma rodada")
    blocking = [f.model_dump() for f in doc.findings
                if f.severity == "important" and f.status == "open" and 2 * f.votes > f.voters]
    for f in blocking:
        problems.append(f"{f['id']}: achado important aberto em {f['path']}:{f['line']}")
    dispositions = {d: sum(f.disposition == d for f in doc.findings) for d in ("wrong", "intentional", "irrelevant")}
    summary = {"round": doc.round, "total": len(doc.findings),
               "by_severity": {s: sum(f.severity == s for f in doc.findings)
                               for s in ("important", "nit", "pre_existing")},
               "by_status": {s: sum(f.status == s for f in doc.findings) for s in ("open", "fixed", "dismissed")},
               "dismissed_as": dispositions,
               "without_consensus": sum(2 * f.votes <= f.voters for f in doc.findings)}
    return {**base, "ok": not problems, "state": "REPROVADO" if problems else "APROVADO",
            "source": cfg.findings, "reviewer": doc.reviewer, "problems": problems,
            "blocking": blocking, "stale": stale, "summary": summary}


def render_findings(report: dict) -> str:
    out = ["# Achados de revisor LLM", "", version_line(report), "",
           f"**Estado: {report['state']}** · evidência {report['evidence']} · não conta como "
           "aprovação humana", "", report["scope"] + "."]
    if report["summary"]:
        s = report["summary"]
        out += ["", f"Rodada {s['round']}: {s['total']} achado(s); abertos {s['by_status']['open']}, "
                    f"corrigidos {s['by_status']['fixed']}, descartados {s['by_status']['dismissed']} "
                    f"(errado {s['dismissed_as']['wrong']}, intencional {s['dismissed_as']['intentional']}, "
                    f"irrelevante {s['dismissed_as']['irrelevant']}); sem consenso {s['without_consensus']}."]
    if report["problems"]:
        out += ["", "## Problemas", ""] + [f"- {p}" for p in report["problems"]]
    return "\n".join(out) + "\n"


# --- Correções como casos de avaliação ------------------------------------------------

def fixes(proj: Project, base: str | None = None) -> dict:
    """Commits com SDD-Fix: o critério corrigido, a feature e os arquivos do commit.
    Servem de conjunto para medir se um revisor pegaria o bug na mudança original."""
    span = f"{base}..HEAD" if base else "HEAD"
    try:
        log = _git(proj.root, "log", "--format=%H%x1f%B%x1e", span)
    except GitError as exc:
        raise ArtifactError(str(exc)) from exc
    owner = {c[0]: s.feature for s in proj.specs.values() for c in s.criteria()}
    tests = proj.config.tests.paths if proj.config else []
    rows, unknown = [], []
    for entry in log.split("\x1e"):
        if "\x1f" not in entry:
            continue
        sha, body = entry.strip().split("\x1f", 1)
        ids = sorted({i for line in FIX_TRAILER.findall(body) for i in CRITERION.findall(line)})
        if not ids:
            continue
        changed = [f for f in _git(proj.root, "show", "--name-only", "--format=", "-z", sha).split("\0") if f]
        unknown += [f"{sha[:12]}: {i}" for i in ids if i not in owner]
        rows.append({"commit": sha, "criteria": ids,
                     "features": sorted({owner[i] for i in ids if i in owner}),
                     "files": sorted(changed), "tests": sorted(f for f in changed if matches(f, tests))})
    return {**metadata("fixes"), "ok": not unknown, "range": span, "fixes": rows,
            "problems": [f"SDD-Fix cita critério inexistente: {u}" for u in unknown],
            "scope": "casos para avaliar revisores; um caso não comprova que o revisor detectaria o "
                     "bug. Clone raso pode omitir commits"}
