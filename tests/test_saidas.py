"""Contratos de saída da CLI e de persistência que a mutação expôs como não verificados:
alinhamento de colunas, JSON com acentos legíveis, códigos de saída e casos de borda."""
import copy
import json

import pytest
from typer.testing import CliRunner

from sdd import core
from sdd.artifacts import ArtifactError
from sdd.cli import _constitution, app
from sdd.learning import accept_lesson, add_lesson, adequacy, save
from sdd.workflow import build, render_markdown as render_guide

from test_analise import SPEC, project
from test_complementos import review

runner = CliRunner()


def invoke(root, *args):
    return runner.invoke(app, [*args, "-C", str(root)])


def test_ac_091_colunas_do_check_e_contagem_de_design(tmp_path):
    project(tmp_path)
    out = invoke(tmp_path, "check").stdout
    assert "\nOK         AC-001" in "\n" + out and "OK          AC-001" not in out
    assert "(0 com design)" in invoke(tmp_path, "validate").stdout


def test_ac_091_principio_nao_aplicavel_que_falha_fica_falhou(tmp_path):
    const = {"principles": [{"id": "CONST-01", "rule": "evals", "enforced_by": ["kit:eval"]}]}
    project(tmp_path, constitution=const)
    proj = core.load(tmp_path)
    failed = _constitution(proj, "eval", False)
    assert failed[0]["enforced_by"] == [{"ref": "kit:eval", "state": "FALHOU"}]
    passed = _constitution(proj, "eval", True)
    assert passed[0]["enforced_by"] == [{"ref": "kit:eval", "state": "NÃO_APLICÁVEL"}]


def test_ac_122_json_da_cli_preserva_acentos_e_indentacao(tmp_path):
    project(tmp_path)
    (tmp_path / "t/ação.py").write_text("x = 1\n", encoding="utf-8")
    cited = invoke(tmp_path, "cite", "t/ação.py:1").stdout
    assert '"path": "t/ação.py"' in cited and cited.startswith('{\n  "path"')
    review(tmp_path)
    ok = invoke(tmp_path, "adequacy", "check", "agenda")
    assert ok.exit_code == 0 and "não executa testes" in ok.stdout and '\n  "command"' in ok.stdout


def test_ac_123_licoes_aceitam_causa_curta_e_gravam_acentos(tmp_path):
    project(tmp_path)
    value = add_lesson(tmp_path, "*", "x", "consultar persistência", ["t/test_x.py:1"])
    assert value.cause == "x"
    assert "consultar persistência" in (tmp_path / "specs/lessons.yaml").read_text(encoding="utf-8")
    listed = invoke(tmp_path, "lesson", "list").stdout
    assert "persistência" in listed and listed.startswith('{\n  "version"')
    with pytest.raises(ArtifactError, match="revisor vazio"):
        accept_lesson(tmp_path, value.id, "  ")


def test_ac_122_item_adequado_sem_assercao_reprova(tmp_path):
    project(tmp_path)
    path, value = review(tmp_path)
    value["items"][0]["assertion"] = " "
    save(tmp_path, path, value)
    problems = adequacy(tmp_path, "agenda")["problems"]
    assert problems == [f"{value['items'][0]['criterion']}: adequação pendente ou insuficiente"]


def test_ac_097_cerca_e_indentacao_do_contexto_do_guia(tmp_path):
    project(tmp_path)
    md = render_guide(build(core.load(tmp_path), "agenda", "plan"))
    assert "\n```json\n{\n  \"spec\": {\n    \"feature\": \"agenda\"" in md and "````" not in md
    spec = copy.deepcopy(SPEC)
    spec["summary"] = "usa ``` dentro do texto"
    project(tmp_path, spec)
    md = render_guide(build(core.load(tmp_path), "agenda", "plan"))
    assert "\n````json\n" in md and "\n`````json\n" not in md
