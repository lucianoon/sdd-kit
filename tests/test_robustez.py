"""Comportamentos que o próprio `sdd mutate` mostrou sem verificação."""
import sys

from typer.testing import CliRunner

from sdd import core
from sdd.cli import app

from test_mutation import FORTE, project as mutation_project
from test_sdd import make

runner = CliRunner()
PY = sys.executable


def test_sem_argumentos_mostra_ajuda():
    r = runner.invoke(app, [])
    assert "check" in r.output and "validate" in r.output


def test_erros_vao_para_stderr(tmp_path):
    make(tmp_path, "def test_qualquer(): pass\n")  # AC-001 sem teste
    r = runner.invoke(app, ["check", "-C", str(tmp_path)])
    assert "ERRO  AC-001" in r.stderr
    assert "ERRO" not in r.stdout


def test_mutate_pode_rodar_duas_vezes(tmp_path):
    mutation_project(tmp_path, FORTE)
    assert runner.invoke(app, ["mutate", "-C", str(tmp_path)]).exit_code == 0
    assert runner.invoke(app, ["mutate", "-C", str(tmp_path)]).exit_code == 0


def test_saida_longa_guarda_o_final(tmp_path):
    rc, out = core.run(f"{PY} -c \"print('x' * 9000 + 'FIM')\"", tmp_path)
    assert rc == 0
    assert len(out) == 4000
    assert out.rstrip().endswith("FIM")


def test_relatorio_marca_criterio_sem_teste():
    report = {"ok": False, "problems": [], "gates": [], "criteria": [
        {"feature": "f", "origin": "REQ-001", "id": "AC-001", "text": "t",
         "verdict": "SEM_TESTE", "tests": []}]}
    assert "| SEM_TESTE | — |" in core.render_markdown(report)
