"""Tamanho da feature, premissas/perguntas abertas e registro de decisões."""
import copy
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from sdd import core
from sdd.cli import app

from test_diff import commit, git, run_diff, write  # noqa: F401  (fixture repo abaixo)

runner = CliRunner()

SPEC = {
    "feature": "pedidos", "version": 1, "size": "small",
    "requirements": [{"id": "REQ-001", "description": "d",
                      "acceptance": [{"id": "AC-001", "given": "g", "when": "w", "then": "t"}]}],
}
DECISIONS = {"decisions": [
    {"id": "AD-001", "title": "t", "decision": "d", "rationale": "r",
     "status": "superseded", "superseded_by": "AD-002"},
    {"id": "AD-002", "title": "t", "decision": "d", "rationale": "r"},
]}


def project(root: Path, spec: dict, decisions: dict | None = None):
    (root / "specs/features/FEATURE-001").mkdir(parents=True)
    (root / "specs/sdd.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(
        {"tests": {"command": "true", "junit": ".sdd/j.xml"}, "require_design": True}))
    (root / "specs/features/FEATURE-001/spec.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(spec, allow_unicode=True))
    if decisions is not None:
        (root / "specs/decisions.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(decisions))
    return "\n".join(core.load(root).errors)


def spec(**over) -> dict:
    s = copy.deepcopy(SPEC)
    s.update(over)
    return s


# --- REQ-007: rigor proporcional ao tamanho ------------------------------------

def test_ac_022_small_sem_design_e_valido(tmp_path):
    assert project(tmp_path, spec(size="small")) == ""


def test_ac_022_large_sem_design_e_erro(tmp_path):
    assert "obrigatória para size 'large'" in project(tmp_path, spec(size="large"))


def test_ac_022_size_ausente_assume_large(tmp_path):
    s = spec()
    s.pop("size")
    assert "obrigatória para size 'large'" in project(tmp_path, s)


def test_ac_023_small_que_altera_muitos_arquivos_reprova(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, "specs/sdd.yaml", "tests: {command: 'true', junit: x}\ncode: ['src/**']\n")
    write(tmp_path, "specs/features/FEATURE-001/spec.yaml",
          yaml.safe_dump(spec(paths=["src/pedidos/**"])))
    commit(tmp_path, "base")
    git(tmp_path, "checkout", "-qb", "pr")
    for i in range(4):
        write(tmp_path, f"src/pedidos/m{i}.py", "x = 1\n")
    write(tmp_path, "specs/features/FEATURE-001/spec.yaml",
          yaml.safe_dump(spec(version=2, paths=["src/pedidos/**"])))
    commit(tmp_path)
    r = runner.invoke(app, ["diff", "-b", "main", "-C", str(tmp_path)])
    assert r.exit_code == 1
    assert "marcada como small mas alterou 4 arquivos" in r.output


# --- REQ-008: closure gate ---------------------------------------------------------

def test_ac_024_pergunta_aberta_bloqueia(tmp_path):
    e = project(tmp_path, spec(open_questions=[{"question": "pode editar após pago?"}]))
    assert "pergunta aberta sem resposta: pode editar após pago?" in e


def test_ac_024_pergunta_respondida_libera(tmp_path):
    assert project(tmp_path, spec(open_questions=[{"question": "q", "answer": "não"}])) == ""


def test_ac_025_premissa_incompleta_e_erro(tmp_path):
    e = project(tmp_path, spec(assumptions=[{"assumption": "moeda", "chosen": "BRL"}]))
    assert "rationale" in e


# --- REQ-009: decisões do projeto ---------------------------------------------------

def test_ac_026_decisao_inexistente_e_erro(tmp_path):
    assert "decisão AD-009 não existe" in project(tmp_path, spec(decisions=["AD-009"]), DECISIONS)


def test_ac_027_decisao_substituida_e_erro(tmp_path):
    e = project(tmp_path, spec(decisions=["AD-001"]), DECISIONS)
    assert "AD-001 foi substituída por AD-002" in e


def test_ac_027_decisao_ativa_e_valida(tmp_path):
    assert project(tmp_path, spec(decisions=["AD-002"]), DECISIONS) == ""


def test_ac_028_superseded_sem_substituta_e_erro(tmp_path):
    bad = copy.deepcopy(DECISIONS)
    bad["decisions"][0].pop("superseded_by")
    assert "superseded_by" in project(tmp_path, spec(), bad)


def test_ac_028_substituta_inexistente_e_erro(tmp_path):
    bad = copy.deepcopy(DECISIONS)
    bad["decisions"][0]["superseded_by"] = "AD-099"
    assert "superseded_by AD-099 inexistente" in project(tmp_path, spec(), bad)
