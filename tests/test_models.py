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
