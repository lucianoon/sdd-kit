import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdd import core
from sdd.cli import app

runner = CliRunner()
PY = sys.executable

SPEC = """\
feature: {feature}
version: 1
requirements:
  - id: {req}
    description: d
    acceptance:
      - {{id: {ac}, given: g, when: w, then: t}}
quality_gates: [{gates}]
"""


def make(root: Path, test_body: str, gates: str = "", gate_cmd: str | None = None, specs=None):
    """Projeto mínimo cujo 'runner de testes' é o pytest de verdade."""
    (root / "specs").mkdir()
    gate_yaml = f"\ngates:\n  g1: '{gate_cmd}'" if gate_cmd else ""
    (root / "specs/sdd.yaml").write_text(encoding="utf-8", data=
        f"version: 1\ntests:\n  command: '{PY} -m pytest -q -p no:cacheprovider --junitxml=.sdd/junit.xml t'\n"
        f"  junit: .sdd/junit.xml{gate_yaml}\n"
    )
    for i, (feat, req, ac) in enumerate(specs or [("f1", "REQ-001", "AC-001")], 1):
        d = root / f"specs/features/FEATURE-{i:03d}"
        d.mkdir(parents=True)
        (d / "spec.yaml").write_text(encoding="utf-8", data=SPEC.format(feature=feat, req=req, ac=ac, gates=gates))
    (root / "t").mkdir()
    (root / "t/test_x.py").write_text(encoding="utf-8", data=test_body)
    return root


def test_ac_001_projeto_valido_sem_erros(tmp_path):
    proj = core.load(make(tmp_path, ""))
    assert proj.errors == []
    assert len(proj.specs) == 1


def test_ac_002_id_duplicado_e_erro(tmp_path):
    make(tmp_path, "", specs=[("f1", "REQ-001", "AC-001"), ("f2", "REQ-002", "AC-001")])
    errors = core.load(tmp_path).errors
    assert any("AC-001 duplicado" in e for e in errors)


def test_ac_003_gate_indefinido_e_erro(tmp_path):
    make(tmp_path, "", gates="inexistente")
    errors = core.load(tmp_path).errors
    assert any("gate 'inexistente' não definido" in e for e in errors)


def test_ac_004_criterio_sem_teste_reprova(tmp_path):
    make(tmp_path, "def test_qualquer(): pass\n")
    report = core.check(core.load(tmp_path))
    assert not report["ok"]
    assert report["criteria"][0]["verdict"] == "SEM_TESTE"


def test_ac_005_teste_falhando_reprova(tmp_path):
    make(tmp_path, "def test_ac_001_x(): assert False\n")
    report = core.check(core.load(tmp_path))
    assert not report["ok"]
    assert report["criteria"][0]["verdict"] == "FALHOU"


def test_ac_006_tudo_passando_aprova_e_grava_relatorio(tmp_path):
    make(tmp_path, "def test_ac_001_x(): pass\n")
    result = runner.invoke(app, ["check", "-C", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "APROVADO" in (tmp_path / ".sdd/report.md").read_text(encoding="utf-8")
    assert (tmp_path / ".sdd/report.json").exists()


def test_ac_007_id_orfao_em_teste_reprova(tmp_path):
    make(tmp_path, "def test_ac_001_x(): pass\ndef test_ac_999_y(): pass\n")
    report = core.check(core.load(tmp_path))
    assert not report["ok"]
    assert any(p.startswith("AC-999") for p in report["problems"])


def test_ac_008_gate_falhando_reprova(tmp_path):
    make(tmp_path, "def test_ac_001_x(): pass\n", gates="g1", gate_cmd=f"{PY} -c \"raise SystemExit(3)\"")
    report = core.check(core.load(tmp_path))
    assert all(r["verdict"] == "OK" for r in report["criteria"])
    assert not report["ok"]
    assert report["gates"][0]["ok"] is False


def test_ac_009_init_gera_projeto_valido(tmp_path):
    assert runner.invoke(app, ["init", "-C", str(tmp_path)]).exit_code == 0
    result = runner.invoke(app, ["validate", "-C", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "AGENTS.md").exists()


def test_pulado_nao_conta_como_evidencia(tmp_path):
    make(tmp_path, "import pytest\n@pytest.mark.skip\ndef test_ac_001_x(): pass\n")
    report = core.check(core.load(tmp_path))
    assert report["criteria"][0]["verdict"] == "PULADO"
    assert not report["ok"]


def test_campo_desconhecido_e_rejeitado(tmp_path):
    make(tmp_path, "")
    f = tmp_path / "specs/features/FEATURE-001/spec.yaml"
    f.write_text(encoding="utf-8", data=f.read_text(encoding="utf-8") + "campo_inventado: 1\n")
    assert core.load(tmp_path).errors
