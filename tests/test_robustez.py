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


def test_check_pode_rodar_duas_vezes(tmp_path):
    make(tmp_path, "def test_ac_001_x(): pass\n")
    assert runner.invoke(app, ["check", "-C", str(tmp_path)]).exit_code == 0
    assert runner.invoke(app, ["check", "-C", str(tmp_path)]).exit_code == 0


def test_report_json_guarda_acentos_legiveis(tmp_path):
    make(tmp_path, "def test_ac_001_x(): pass\n")
    spec = tmp_path / "specs/features/FEATURE-001/spec.yaml"
    spec.write_text(encoding="utf-8", data=spec.read_text(encoding="utf-8").replace("then: t", "then: pedido é persistido"))
    runner.invoke(app, ["check", "-C", str(tmp_path)])
    assert "pedido é persistido" in (tmp_path / ".sdd/report.json").read_text(encoding="utf-8")


def test_risco_mitigado_por_regra_arch_mostra_estado():
    base = {"ok": True, "problems": [], "gates": [], "criteria": [],
            "risks": [{"feature": "f", "area": "other", "severity": "low", "description": "acoplamento",
                       "mitigated_by": ["ARCH-001"], "accepted": ""}]}
    ok = core.render_markdown({**base, "architecture": {"rules": ["ARCH-001"], "violations": [],
                                                         "exceptions": [], "files": 3}})
    assert "ARCH-001 (OK)" in ok
    bad = core.render_markdown({**base, "architecture": {"rules": ["ARCH-001"], "files": 3, "exceptions": [],
                                                          "violations": [{"rule": "ARCH-001", "file": "a.py",
                                                                          "line": 1, "import": "x"}]}})
    assert "ARCH-001 (VIOLADA)" in bad


def test_junit_em_pastas_aninhadas_inexistentes(tmp_path):
    # ex.: Gradle/Maven gravam em build/test-results/...; as pastas ainda não existem
    make(tmp_path, "def test_ac_001_x(): pass\n")
    cfg = tmp_path / "specs/sdd.yaml"
    cfg.write_text(encoding="utf-8", data=cfg.read_text(encoding="utf-8").replace(
        ".sdd/junit.xml", "build/test-results/junit.xml"))
    report = core.check(core.load(tmp_path))
    assert report["ok"], report["problems"]
