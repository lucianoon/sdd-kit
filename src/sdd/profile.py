"""Perfil de agentes: a SPEC-BASE como catálogo verificável.

O catálogo (profiles/agentes.yaml) lista os requisitos de referência por módulo. O projeto
declara em specs/agents.yaml quais módulos estão ativos e, para cada requisito ativo, os IDs
que o provam (AC, NFR, EVAL, ARCH) ou "não se aplica" com motivo. O validate cobra a
matriz; o check mostra o estado de cada evidência.
"""
from __future__ import annotations

from functools import lru_cache
from importlib import resources

import yaml

from .models import AgentsProfile, Catalog, NotApplicable

AGENTS_PATH = "specs/agents.yaml"
DETERMINISTIC = ("AC-", "NFR-", "ARCH-")


@lru_cache(maxsize=None)
def catalog(name: str = "agentes") -> Catalog:
    text = resources.files("sdd").joinpath(f"profiles/{name}.yaml").read_text(encoding="utf-8")
    return Catalog.model_validate(yaml.safe_load(text))


def known_ids(proj) -> set[str]:
    ids = {r.id for r in proj.arch}
    for spec in proj.specs.values():
        ids.update(c[0] for c in spec.criteria())
        ids.update(e.id for e in spec.evals)
    return ids


def validate(proj, prof: AgentsProfile) -> tuple[list[str], list[str]]:
    """(erros, avisos) da matriz de aplicabilidade e da cobertura."""
    cat = catalog(prof.profile)
    errors: list[str] = []
    warnings: list[str] = []
    where = AGENTS_PATH
    pending_is_error = prof.stage != "local"

    for key in prof.modules:
        if key not in cat.modules:
            errors.append(f"{where}: módulo '{key}' não existe no perfil {prof.profile} "
                          f"(válidos: {', '.join(cat.modules)})")
    for key, mod in cat.modules.items():
        st = prof.state(key)
        if st is None:
            msg = f"{where}: módulo {key} ({mod.name}) não declarado; marque ativo, inativo ou pendente"
            (errors if mod.mandatory or pending_is_error else warnings).append(msg)
            continue
        if mod.mandatory and st.status != "ativo":
            errors.append(f"{where}: módulo {key} ({mod.name}) é obrigatório e precisa estar ativo")
        if st.status == "inativo" and not st.reason.strip():
            errors.append(f"{where}: módulo {key} inativo precisa de motivo (reason)")
        if st.status == "pendente":
            msg = f"{where}: módulo {key} ({mod.name}) pendente: decida antes do estágio piloto"
            (errors if pending_is_error else warnings).append(msg)
    if prof.stage == "producao":
        p = prof.state("P")
        if p is None or p.status != "ativo":
            errors.append(f"{where}: estágio producao exige o módulo P (produção e escala) ativo")

    reqs = {r.id: (key, r) for key, mod in cat.modules.items() for r in mod.requirements}
    ids = known_ids(proj)
    for rid in prof.coverage:
        if rid not in reqs:
            errors.append(f"{where}: coverage cita requisito '{rid}' que não existe no catálogo")
    for rid, (key, req) in reqs.items():
        st = prof.state(key)
        if st is None or st.status != "ativo":
            continue
        cov = prof.coverage.get(rid)
        label = f"{rid} ({req.title})"
        if cov is None or cov == []:
            errors.append(f"{where}: {label} sem evidência; liste AC/NFR/EVAL/ARCH ou not_applicable")
            continue
        if isinstance(cov, NotApplicable):
            if req.critical:
                errors.append(f"{where}: {label} é crítico e não aceita not_applicable com o módulo {key} ativo")
            continue
        for ref in cov:
            if ref not in ids:
                errors.append(f"{where}: {label} cita '{ref}', que não existe em nenhuma spec nem regra ARCH")
        if req.critical and not any(ref.startswith(DETERMINISTIC) for ref in cov):
            errors.append(f"{where}: {label} é crítico: exige ao menos uma evidência determinística "
                          "(AC, NFR ou ARCH); eval sozinho não basta")
    return errors, warnings


def matrix(proj, prof: AgentsProfile, verdicts: dict[str, str]) -> list[dict]:
    """Linha por requisito, com o estado das evidências (para o relatório do check)."""
    out = []
    for key, mod in catalog(prof.profile).modules.items():
        st = prof.state(key)
        status = st.status if st else "não declarado"
        for req in mod.requirements:
            cov = prof.coverage.get(req.id)
            if status != "ativo":
                state, refs = status.upper(), []
            elif isinstance(cov, NotApplicable):
                state, refs = f"N/A: {cov.not_applicable}", []
            else:
                refs = [{"id": r, "verdict": verdicts.get(r, "ver sdd eval" if r.startswith("EVAL-") else "?")}
                        for r in (cov or [])]
                # "?" = ainda não verificado (ex.: `sdd profile` não roda testes): declarado, não falho
                bad = [r for r in refs if r["verdict"] not in ("OK", "ver sdd eval", "?")]
                state = "SEM_EVIDÊNCIA" if not refs else ("FALHA" if bad else "COBERTO")
            out.append({"module": key, "module_name": mod.name, "id": req.id, "title": req.title,
                        "critical": req.critical, "state": state, "evidence": refs})
    return out


def skeleton(name: str = "agentes") -> str:
    """specs/agents.yaml inicial: núcleo ativo, demais pendentes, cobertura a preencher."""
    cat = catalog(name)
    lines = [
        "# Perfil de agentes: quais módulos se aplicam e o que prova cada requisito.",
        "# Catálogo completo: `sdd profile --catalog`. Estado atual: `sdd profile`.",
        f"profile: {name}",
        "stage: local          # local | piloto | producao (pendências só são toleradas em local)",
        "modules:",
    ]
    for key, mod in cat.modules.items():
        status = "ativo" if mod.mandatory else "pendente"
        lines.append(f"  {key}: {status:<9} # {mod.name}. Ative quando: {mod.activate_when.strip()}")
    lines += ["", "# Para cada requisito de módulo ativo: IDs que o provam, ou {not_applicable: motivo}.",
              "# Críticos (*) exigem ao menos um AC, NFR ou ARCH e não aceitam not_applicable.",
              "coverage:"]
    for key, mod in cat.modules.items():
        if not mod.mandatory:
            continue
        for req in mod.requirements:
            star = "*" if req.critical else " "
            lines.append(f"  {req.id}: []  # {star} {req.title}. Evidência: {req.evidence}")
    return "\n".join(lines) + "\n"
