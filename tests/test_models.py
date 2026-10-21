"""Regras do schema e valores padrão que são decisões de segurança."""
import copy

import pytest
from pydantic import ValidationError

from sdd.models import ArchRule, Config, Eval, Number


def test_numero_com_min_maior_que_max_e_invalido():
    with pytest.raises(ValidationError, match="min maior que max"):
        Number(metric="m", min=10, max=5, unit="ms", source="s")
    Number(metric="m", min=5, max=10, unit="ms", source="s")
    Number(metric="m", min=5, max=5, unit="ms", source="s")  # igual é válido


def test_threshold_com_min_maior_que_max_e_invalido():
    base = {"id": "EVAL-001", "metric": "m", "dataset": "d.jsonl", "min_cases": 1}
    with pytest.raises(ValidationError, match="min maior que max"):
        Eval(**base, threshold={"min": 0.9, "max": 0.5})
    Eval(**base, threshold={"min": 0.5, "max": 0.9})
    Eval(**base, threshold={"min": 0.5, "max": 0.5})


def test_regra_arch_aceita_so_forbid_ou_so_forbid_paths():
    ArchRule.model_validate({"id": "ARCH-001", "description": "d", "from": ["a/**"], "forbid": ["x"]})
    ArchRule.model_validate({"id": "ARCH-001", "description": "d", "from": ["a/**"], "forbid_paths": ["b/**"]})


def test_regra_arch_so_aceita_a_chave_from():
    with pytest.raises(ValidationError):
        ArchRule.model_validate({"id": "ARCH-001", "description": "d", "sources": ["a/**"], "forbid": ["x"]})


def test_padroes_conservadores_da_config():
    cfg = Config.model_validate({"tests": {"command": "c", "junit": "j"}})
    assert cfg.require_design is False          # opt-in: projeto existente não quebra ao adotar
    assert cfg.evals.allow_llm_judge is False   # juiz LLM só por decisão explícita (AD-004)
    assert cfg.design_required_for == ["large", "complex"]
    assert cfg.tests.timeout == 3600


# Limites do formato YAML das specs: contrato público. Mudar um valor muda o que é uma spec
# válida em todo projeto que adota o kit; a mudança tem que aparecer aqui, de propósito.
LIMITES = {
    "Alternative.name": ("min_length", 1), "ArchRule.description": ("min_length", 1),
    "ArchRule.sources": ("min_length", 1), "Assumption.assumption": ("min_length", 1),
    "Assumption.chosen": ("min_length", 1), "Assumption.rationale": ("min_length", 1),
    "CatalogModule.requirements": ("min_length", 1), "Config.small_max_files": ("ge", 1),
    "Constitution.principles": ("min_length", 1), "CostCeiling.unit": ("min_length", 1),
    "CostCeiling.value": ("gt", 0), "CostCeiling.window": ("min_length", 1),
    "DataFlow.egress": ("min_length", 1), "DataFlow.ingress": ("min_length", 1),
    "Decision.decision": ("min_length", 1), "Decision.rationale": ("min_length", 1),
    "Decision.title": ("min_length", 1), "Dependency.covered_by": ("min_length", 1),
    "Dependency.fallback": ("min_length", 1), "Dependency.name": ("min_length", 1),
    "Dependency.timeout_ms": ("ge", 1), "Design.alternatives": ("min_length", 2),
    "Design.numbers": ("min_length", 1), "Design.risks": ("min_length", 1),
    "Egress.to": ("min_length", 1), "Eval.dataset": ("min_length", 1),
    "Eval.max_run_spread": ("ge", 0), "Eval.metric": ("min_length", 1),
    "Eval.min_cases": ("ge", 1), "Eval.runs": ("ge", 1), "EvalsConfig.timeout": ("ge", 1),
    "Ingress.frequency": ("min_length", 1), "Ingress.via": ("min_length", 1),
    "Limits.concurrency": ("ge", 1), "Limits.deadline_s": ("ge", 1),
    "Limits.max_input_tokens": ("ge", 1), "Limits.max_output_tokens": ("ge", 1),
    "Limits.max_steps": ("ge", 1), "Limits.max_tool_calls": ("ge", 0),
    "MutationConfig.max_mutants": ("ge", 1), "MutationConfig.min_score": ("le", 1),
    "MutationConfig.timeout": ("ge", 1), "NotApplicable.not_applicable": ("min_length", 1),
    "Number.metric": ("min_length", 1), "Number.source": ("min_length", 1),
    "Number.unit": ("min_length", 1), "OpenQuestion.question": ("min_length", 1),
    "Principle.rule": ("min_length", 1), "Requirement.acceptance": ("min_length", 1),
    "Retry.max_attempts": ("ge", 1), "ReviewConfig.max_rounds": ("ge", 1), "Risk.description": ("min_length", 1),
    "Spec.requirements": ("min_length", 1), "Spec.version": ("ge", 1),
    "Task.done_when": ("min_length", 1), "Task.origin": ("min_length", 1),
    "Task.title": ("min_length", 1), "TestsConfig.timeout": ("ge", 1),
}


def _limites() -> dict:
    import inspect

    from pydantic import BaseModel

    import sdd.models as m

    out = {}
    for name, cls in vars(m).items():
        if not (inspect.isclass(cls) and issubclass(cls, BaseModel) and cls.__module__ == m.__name__):
            continue
        for field, info in cls.model_fields.items():
            if field not in cls.__annotations__:
                continue  # herdado: conferido na classe que declara
            for meta in info.metadata:
                for attr in ("min_length", "max_length", "ge", "gt", "le", "lt"):
                    if getattr(meta, attr, None) is not None:
                        out[f"{name}.{field}"] = (attr, getattr(meta, attr))
    return out


def test_limites_do_schema_sao_contrato():
    assert _limites() == LIMITES


def test_valor_no_limite_e_aceito_e_abaixo_dele_e_recusado():
    from sdd.models import Assumption, Dependency, Ingress

    Ingress(via="h", frequency="1")  # um caractere basta
    with pytest.raises(ValidationError):
        Ingress(via="", frequency="1")
    Assumption(assumption="a", chosen="b", rationale="c")
    with pytest.raises(ValidationError):
        Assumption(assumption="a", chosen="b", rationale="")
    dep = {"name": "n", "kind": "process", "retry": {"max_attempts": 1, "backoff": "none"},
           "fallback": "f", "side_effects": False, "idempotent": True, "covered_by": ["AC-001"]}
    Dependency(**dep, timeout_ms=1)
    with pytest.raises(ValidationError):
        Dependency(**dep, timeout_ms=0)
