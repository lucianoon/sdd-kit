"""Camada de CLI: códigos de saída, stderr para erros, JSON legível e filtros."""
import json
import sys

import yaml
from typer.testing import CliRunner

from sdd.cli import app

from test_evals import project as eval_project, ev_with
from test_mutation import FORTE, FRACO, project as mut_project
from test_sdd import make

runner = CliRunner()
PY = sys.executable


def run(*args):
    return runner.invoke(app, list(args))


def test_sem_argumentos_mostra_ajuda_sem_autocompletar():
    r = run()
    assert "specify" in r.output and "--install-completion" not in r.output


def test_ac_091_version_tem_precedencia_sobre_subcomando_invalido():
    from sdd import __version__

    r = run("--version", "comando-inexistente")
    assert r.exit_code == 0 and r.stdout.strip() == f"sdd-kit {__version__}"
    r = run("--version", "--help")
    assert r.exit_code == 0 and r.stdout.strip() == f"sdd-kit {__version__}"


def test_erros_de_specify_e_validate_vao_para_stderr(tmp_path):
    r = run("specify", "Nome_Ruim", "-C", str(tmp_path))
    assert r.exit_code == 2 and "nome inválido" in r.stderr and "ERRO" not in r.stdout
    r = run("validate", "-C", str(tmp_path))  # projeto sem specs
    assert r.exit_code == 1 and "ERRO" in r.stderr and "ERRO" not in r.stdout


def test_specify_lista_os_ids_alocados(tmp_path):
    r = run("specify", "primeira", "-C", str(tmp_path))
    assert "IDs      REQ: REQ-001  AC: AC-001" in r.stdout


def test_erros_de_git_vao_para_stderr(tmp_path):
    make(tmp_path, "def test_ac_001(): pass\n")
    r = run("diff", "--base", "nao-existe", "-C", str(tmp_path))
    assert r.exit_code == 2 and "ERRO" in r.stderr and "ERRO" not in r.stdout
    r = run("mutate", "--base", "nao-existe", "-C", str(tmp_path))
    assert r.exit_code == 2 and "ERRO" in r.stderr


def test_mutate_sem_feature_com_paths(tmp_path):
    make(tmp_path, "def test_ac_001(): pass\n")
    r = run("mutate", "-C", str(tmp_path))
    assert r.exit_code == 2 and "nenhuma feature com `paths`" in r.stderr


def test_mutate_filtra_por_feature(tmp_path):
    mut_project(tmp_path, FORTE)
    extra = tmp_path / "specs/features/FEATURE-002"
    extra.mkdir()
    spec = yaml.safe_load((tmp_path / "specs/features/FEATURE-001/spec.yaml").read_text(encoding="utf-8"))
    spec.update(feature="outra", requirements=[{**spec["requirements"][0], "id": "REQ-002", "acceptance": [
        {"id": "AC-002", "given": "g", "when": "w", "then": "t"}]}])
    (extra / "spec.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(spec))
    r = run("mutate", "--feature", "outra", "--max", "1", "-C", str(tmp_path))
    assert "== outra" in r.output and "== calc" not in r.output
    r = run("mutate", "--feature", "inexistente", "-C", str(tmp_path))
    assert r.exit_code == 2


def test_mutate_erro_de_suite_vai_para_stderr(tmp_path):
    mut_project(tmp_path, FORTE.replace("is True", "is False", 1))
    r = run("mutate", "-C", str(tmp_path))
    assert r.exit_code == 2 and "não passa sem mutações" in r.stderr


def test_mutate_avisa_quando_nenhum_mutante_morre(tmp_path):
    mut_project(tmp_path, "def test_nada():\n    pass\n")
    r = run("mutate", "-C", str(tmp_path))
    assert "AVISO nenhum mutante morreu" in r.output
    forte = tmp_path / "forte"
    forte.mkdir()
    mut_project(forte, FORTE)
    assert "AVISO" not in run("mutate", "-C", str(forte)).output


def test_mutation_json_guarda_acentos_legiveis(tmp_path):
    mut_project(tmp_path, FRACO, code='def maior(a, b):\n    return "não" if a > b else "sim"\n\n\ndef desconto(t, v):\n    return t\n')
    run("mutate", "-C", str(tmp_path))
    text = (tmp_path / ".sdd/mutation.json").read_text(encoding="utf-8")
    assert "não" in text and "\\u00e3" not in text


def test_arch_problema_vai_para_stderr(tmp_path):
    from test_arquitetura import project as arch_project
    arch_project(tmp_path, {"src/core/a.py": "x = 1\n"})  # regra aponta para src/domain inexistente
    r = run("arch", "-C", str(tmp_path))
    assert r.exit_code == 1 and "nenhum arquivo casa" in r.stderr


def test_eval_cli_marca_juiz_llm_e_guarda_acentos(tmp_path):
    eval_project(tmp_path, ev_with(judge="llm", metric="precisão_da_tool"), allow_llm=True)
    r = run("eval", "-C", str(tmp_path))
    assert r.exit_code == 0 and "[juiz LLM]" in r.stdout
    assert "precisão_da_tool" in (tmp_path / ".sdd/eval.json").read_text(encoding="utf-8")
    det = tmp_path / "det"
    det.mkdir()
    eval_project(det)
    assert "[juiz LLM]" not in run("eval", "-C", str(det)).stdout


def test_eval_problema_vai_para_stderr(tmp_path):
    from test_evals import lines_for
    eval_project(tmp_path, plan=lines_for([0.5, 0.5, 0.5]))
    r = run("eval", "-C", str(tmp_path))
    assert r.exit_code == 1 and "FORA_DO_LIMITE" in r.stderr


def test_schema_sai_com_acentos_legiveis():
    r = run("schema")
    assert r.exit_code == 0 and "Número" in r.stdout and "\\u00fa" not in r.stdout
    json.loads(r.stdout)
