"""Análise de consistência determinística: tarefas, constituição e critérios vagos.

É a etapa "análise" do SDD (cruzar constituição, spec, plano e tarefas antes de implementar)
feita por ferramenta, não pelo julgamento do agente.
"""
from __future__ import annotations

import re
import unicodedata

from .models import ENFORCERS_KIT, Spec

CONSTITUTION_PATH = "specs/constitution.yaml"

# Termos que não definem resultado observável quando aparecem sem nenhum número.
VAGUE_TERMS = [
    "rápido", "rápida", "rapidamente", "lento", "seguro", "segura", "seguramente",
    "corretamente", "correto", "correta", "adequado", "adequada", "adequadamente",
    "eficiente", "eficientemente", "robusto", "robusta", "intuitivo", "intuitiva",
    "amigável", "fácil", "facilmente", "otimizado", "otimizada", "escalável", "confiável",
    "bem", "bom", "boa", "melhor", "razoável", "satisfatório", "satisfatória", "aceitável",
    "fast", "quickly", "slow", "secure", "securely", "correctly", "properly", "efficient",
    "robust", "intuitive", "easy", "easily", "user-friendly", "scalable", "reliable",
    "appropriate", "reasonable", "good", "better", "acceptable",
]


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


# As âncoras de palavra inteira dispensam ordenar as alternativas por tamanho.
_VAGUE_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted({re.escape(_fold(t)) for t in VAGUE_TERMS}))
                       + r")(?![\w-])")


def vague_terms(text: str) -> list[str]:
    """Termos vagos de um critério que não traz nenhum valor numérico."""
    if re.search(r"\d", text):
        return []
    return sorted(set(_VAGUE_RE.findall(_fold(text))))


def check_criteria(rel: str, spec: Spec) -> list[str]:
    out = []
    for req in spec.requirements:
        for ac in req.acceptance:
            terms = vague_terms(ac.then)
            if terms:
                out.append(f"{rel}: {ac.id}: critério vago ({', '.join(terms)}) sem valor observável; "
                           "diga o que se mede e quanto (ex.: 'em até 300 ms com 10 mil registros')")
    return out


def _cycle(tasks: dict[str, list[str]]) -> list[str] | None:
    """Um ciclo de dependências (lista de IDs), se houver."""
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(t: str) -> list[str] | None:
        state[t] = 1
        stack.append(t)
        for d in tasks.get(t, []):
            if d not in tasks:
                continue
            if state.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if d not in state:
                found = visit(d)
                if found:
                    return found
        state[t] = 2
        stack.pop()
        return None

    for t in tasks:
        if t not in state:
            found = visit(t)
            if found:
                return found
    return None


def check_tasks(rel: str, spec: Spec, global_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not spec.tasks:
        return errors
    local = {r.id for r in spec.requirements} | {c[0] for c in spec.criteria()} | {e.id for e in spec.evals}
    valid = local | global_ids
    ids = [t.id for t in spec.tasks]
    for tid in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"{rel}: tarefa {tid} duplicada")
    deps = {t.id: t.depends_on for t in spec.tasks}
    for t in spec.tasks:
        for ref in t.origin:
            if ref not in valid:
                errors.append(f"{rel}: {t.id} tem origem '{ref}' inexistente (tarefa sem origem válida)")
        for ref in t.evidence:
            if ref not in valid:
                errors.append(f"{rel}: {t.id} cita evidência '{ref}' inexistente")
        for d in t.depends_on:
            if d not in deps:
                errors.append(f"{rel}: {t.id} depende de '{d}', que não existe nesta spec")
            elif d == t.id:
                errors.append(f"{rel}: {t.id} depende de si mesma")
    cyc = _cycle(deps)
    if cyc and len(cyc) > 2:
        errors.append(f"{rel}: dependências em ciclo: {' → '.join(cyc)}")
    cited = {ref for t in spec.tasks for ref in t.origin + t.evidence}
    for req in spec.requirements:
        for ac in req.acceptance:
            if ac.id not in cited and req.id not in cited:
                errors.append(f"{rel}: {ac.id} não é coberto por nenhuma tarefa (requisito órfão)")
    for cid, _, _ in spec.criteria():
        if cid.startswith("NFR-") and cid not in cited:
            errors.append(f"{rel}: {cid} não é coberto por nenhuma tarefa (requisito órfão)")
    for ev in spec.evals:
        if ev.id not in cited:
            errors.append(f"{rel}: {ev.id} não é coberto por nenhuma tarefa (requisito órfão)")
    return errors


def check_constitution(proj, constitution) -> list[str]:
    from .profile import catalog

    errors: list[str] = []
    where = CONSTITUTION_PATH
    seen: set[str] = set()
    tests = {c[0] for s in proj.specs.values() for c in s.criteria()} | \
            {e.id for s in proj.specs.values() for e in s.evals}
    arch = {r.id for r in proj.arch}
    gates = set(proj.config.gates) if proj.config else set()
    reqs = {r.id: key for key, m in catalog().modules.items() for r in m.requirements}
    for p in constitution.principles:
        if p.id in seen:
            errors.append(f"{where}: princípio {p.id} duplicado")
        seen.add(p.id)
        for ref in p.enforced_by:
            if ref.startswith("gate:"):
                if ref[5:] not in gates:
                    errors.append(f"{where}: {p.id}: gate '{ref[5:]}' não definido em specs/sdd.yaml")
            elif ref.startswith("kit:"):
                if ref[4:] not in ENFORCERS_KIT:
                    errors.append(f"{where}: {p.id}: '{ref}' não é recurso do kit "
                                  f"({', '.join('kit:' + k for k in ENFORCERS_KIT)})")
            elif ref.startswith("profile:"):
                rid = ref[8:]
                key = reqs.get(rid)
                st = proj.agents.state(key) if (proj.agents and key) else None
                if key is None:
                    errors.append(f"{where}: {p.id}: requisito '{rid}' não existe no perfil de agentes")
                elif st is None or st.status != "ativo":
                    errors.append(f"{where}: {p.id}: '{ref}' exige o perfil de agentes com o módulo {key} ativo")
            elif ref.startswith("ARCH-"):
                if ref not in arch:
                    errors.append(f"{where}: {p.id}: regra '{ref}' não existe em specs/architecture.yaml")
            elif ref not in tests:
                errors.append(f"{where}: {p.id}: '{ref}' não é AC, NFR, EVAL, ARCH, gate:, kit: nem profile: válido")
    return errors


def kit_context(proj, completed: dict[str, str]) -> dict[str, str]:
    """Escopo desta execução. Não lê relatórios antigos para inferir aprovação."""
    specs = list(proj.specs.values())
    states = {key: "PENDENTE" for key in ENFORCERS_KIT}
    states.update({
        "validate": "FALHOU" if proj.errors else "OK",
        "design": "OK" if any(s.design for s in specs) else "NÃO_APLICÁVEL",
        "tasks": "OK" if any(s.tasks for s in specs) else "NÃO_APLICÁVEL",
        "dependencies": "OK" if any(s.design and s.design.dependencies for s in specs) else "NÃO_APLICÁVEL",
        "limits": "OK" if any(s.design and s.design.limits for s in specs) else "NÃO_APLICÁVEL",
    })
    applicable = {
        "diff": bool(proj.config and proj.config.code) or any(s.paths or s.evals for s in specs),
        "mutate": any(s.paths for s in specs),
        "eval": any(s.evals for s in specs),
        "arch": bool(proj.arch),
        "profile": proj.agents is not None,
    }
    for key, applies in applicable.items():
        if not applies:
            states[key] = "NÃO_APLICÁVEL"
    states.update(completed)
    return states


def constitution_matrix(constitution, verdicts: dict[str, str], gates: dict[str, bool],
                        profile_states: dict[str, str], kit_states: dict[str, str] | None = None) -> list[dict]:
    rows = []
    for p in constitution.principles:
        refs = []
        for ref in p.enforced_by:
            if ref.startswith("gate:"):
                state = "OK" if gates.get(ref[5:]) else ("FALHOU" if ref[5:] in gates else "PENDENTE")
            elif ref.startswith("kit:"):
                state = (kit_states or {}).get(ref[4:], "DECLARADO")
            elif ref.startswith("profile:"):
                state = profile_states.get(ref[8:], "PENDENTE")
            else:
                state = verdicts.get(ref, "PENDENTE")
            refs.append({"ref": ref, "state": state})
        states = {"NÃO_APLICÁVEL" if r["state"].startswith("N/A:") else r["state"] for r in refs}
        passing = {"OK", "COBERTO", "NÃO APLICÁVEL", "NÃO_APLICÁVEL"}
        bad = states - passing - {"PENDENTE", "DECLARADO"}
        if bad:
            status = "VIOLADO"
        elif not refs:
            status = "MANUAL"
        elif "PENDENTE" in states:
            status = "PENDENTE"
        elif "DECLARADO" in states:
            status = "DECLARADO"
        elif p.manual.strip():
            status = "MANUAL"
        elif states == {"NÃO_APLICÁVEL"}:
            status = "NÃO_APLICÁVEL"
        else:
            status = "APROVADO"
        rows.append({"id": p.id, "rule": p.rule, "status": status, "enforced_by": refs, "manual": p.manual})
    return rows
