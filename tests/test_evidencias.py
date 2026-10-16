"""Alcance de evidências e identificação de relatórios reais dos comandos."""
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from sdd import __version__, core
from sdd.analysis import constitution_matrix
from sdd.cli import app
from sdd.models import Constitution

from test_analise import project
from test_diff import CONFIG, SPEC, git, write, commit
from test_evals import project as eval_project, ev_with
from test_mutation import FORTE, project as mut_project
from test_sdd import make

runner = CliRunner()


def constitution(*refs):
    return {"principles": [{"id": f"CONST-{i:02d}", "rule": ref, "enforced_by": [ref]}
                           for i, ref in enumerate(refs, 1)]}


def test_ac_089_declaracao_nao_e_aprovacao():
    const = Constitution.model_validate(constitution("kit:mutate", "EVAL-001", "gate:segredos"))
    rows = constitution_matrix(const, {}, {}, {})
    assert [r["status"] for r in rows] == ["DECLARADO", "PENDENTE", "PENDENTE"]


def test_ac_089_check_nao_reusa_resultado_antigo_de_mutacao(tmp_path):
    spec = yaml.safe_load(SPEC)
    const = constitution("kit:check", "kit:mutate", "kit:diff", "kit:eval")
    project(tmp_path, spec, constitution=const)
    write(tmp_path, "t/test_x.py", "def test_ac_001(): pass\n")
    write(tmp_path, ".sdd/mutation.json", json.dumps([{"ok": True}]))
    report = core.check(core.load(tmp_path))
    assert report["ok"], report["problems"]
    states = {r["rule"]: r["status"] for r in report["constitution"]}
    assert states == {"kit:check": "APROVADO", "kit:mutate": "PENDENTE",
                      "kit:diff": "PENDENTE", "kit:eval": "NÃO_APLICÁVEL"}


def test_ac_089_revisao_manual_nao_e_aprovada_por_teste():
    const = Constitution.model_validate({"principles": [{"id": "CONST-01", "rule": "r",
        "enforced_by": ["AC-001"], "manual": "revisão no PR"}]})
    assert constitution_matrix(const, {"AC-001": "OK"}, {}, {})[0]["status"] == "MANUAL"


def test_ac_089_eval_aplicavel_nao_executada_fica_pendente(tmp_path):
    spec = yaml.safe_load(SPEC)
    spec["evals"] = [{"id": "EVAL-001", "metric": "accuracy", "dataset": "evals/casos.jsonl",
                       "min_cases": 1, "threshold": {"min": 0.9}}]
    project(tmp_path, spec, constitution=constitution("kit:eval", "EVAL-001"))
    write(tmp_path, "t/test_x.py", "def test_ac_001(): pass\n")
    write(tmp_path, "evals/casos.jsonl", '{"id": "caso-1"}\n')
    report = core.check(core.load(tmp_path))
    assert report["ok"], report["problems"]
    assert [r["status"] for r in report["constitution"]] == ["PENDENTE", "PENDENTE"]


def test_ac_089_mutacao_sem_candidatos_nao_e_evidencia(tmp_path):
    mut_project(tmp_path, FORTE, code="x = y\n")  # nenhum operador nem constante
    write(tmp_path, "specs/constitution.yaml", yaml.safe_dump(constitution("kit:mutate")))
    r = runner.invoke(app, ["mutate", "-C", str(tmp_path)])
    assert r.exit_code == 0, r.output
    report = json.loads((tmp_path / ".sdd/mutation.json").read_text(encoding="utf-8"))
    assert report[0]["mutants"] == []
    assert report[0]["verdict"] == "NÃO_APLICÁVEL"
    assert report[0]["constitution"][0]["status"] == "PENDENTE"


def test_ac_089_dependencias_vazias_sao_nao_aplicaveis(tmp_path):
    from test_design import BASE_SPEC

    project(tmp_path, BASE_SPEC, constitution=constitution("kit:design", "kit:dependencies", "kit:diff"))
    write(tmp_path, "t/test_x.py", "def test_ac_001(): pass\ndef test_nfr_001(): pass\n")
    report = core.check(core.load(tmp_path))
    assert report["ok"], report["problems"]
    assert [r["status"] for r in report["constitution"]] == ["APROVADO", "NÃO_APLICÁVEL", "NÃO_APLICÁVEL"]


def test_ac_089_regra_arch_sem_arquivos_nao_e_aprovada(tmp_path):
    project(tmp_path, constitution=constitution("ARCH-001"), arch={"rules": [
        {"id": "ARCH-001", "description": "sem rede", "from": ["src/inexistente/**"], "forbid": ["httpx"]}]})
    report = core.check(core.load(tmp_path))
    assert report["architecture"]["problems"]
    assert report["constitution"][0]["status"] == "VIOLADO"


def test_ac_089_perfil_distingue_teste_aprovado_eval_pendente_e_dispensa(tmp_path):
    from test_perfil import init, write_agents, set_test_command

    init(tmp_path)
    write_agents(tmp_path, coverage={"N-02": ["EVAL-001"],
                                    "N-01": {"not_applicable": "fora do contrato deste exemplo"}})
    set_test_command(tmp_path)
    write(tmp_path, "t/test_x.py", "def test_ac_001(): pass\ndef test_nfr_001(): pass\n")
    write(tmp_path, "evals/casos.jsonl", '{"id": "caso-1"}\n')
    path = tmp_path / "specs/features/FEATURE-001/spec.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec["evals"] = [{"id": "EVAL-001", "metric": "accuracy", "dataset": "evals/casos.jsonl",
                       "min_cases": 1, "threshold": {"min": 0.9}}]
    spec["tasks"][0]["origin"].append("EVAL-001")
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    write(tmp_path, "specs/constitution.yaml", yaml.safe_dump(
        constitution("profile:N-04", "profile:N-02", "profile:N-01")))
    proj = core.load(tmp_path)
    assert not proj.errors, proj.errors
    report = core.check(proj)
    assert report["ok"], report["problems"]
    assert [r["status"] for r in report["constitution"]] == ["APROVADO", "PENDENTE", "NÃO_APLICÁVEL"]


def test_ac_089_verificacao_parcial_de_mutacao_continua_pendente(tmp_path):
    mut_project(tmp_path, FORTE)
    write(tmp_path, "specs/constitution.yaml", yaml.safe_dump(constitution("kit:mutate")))
    r = runner.invoke(app, ["mutate", "--feature", "calc", "-C", str(tmp_path)])
    assert r.exit_code == 0, r.output
    report = json.loads((tmp_path / ".sdd/mutation.json").read_text(encoding="utf-8"))
    assert report[0]["constitution"][0]["status"] == "PENDENTE"
    r = runner.invoke(app, ["mutate", "-C", str(tmp_path)])
    assert r.exit_code == 0, r.output
    report = json.loads((tmp_path / ".sdd/mutation.json").read_text(encoding="utf-8"))
    assert report[0]["constitution"][0]["status"] == "APROVADO"


@pytest.mark.parametrize("command,filename", [
    ("check", "report"), ("diff", "diff"), ("mutate", "mutation"), ("eval", "eval"), ("arch", "arch"),
])
def test_ac_091_relatorios_identificam_versao_e_comando(tmp_path, command, filename):
    args = [command, "-C", str(tmp_path)]
    if command == "mutate":
        mut_project(tmp_path, FORTE)
    elif command == "eval":
        eval_project(tmp_path)
    elif command == "diff":
        git(tmp_path, "init", "-q", "-b", "main")
        write(tmp_path, "specs/sdd.yaml", CONFIG)
        write(tmp_path, "specs/features/FEATURE-001/spec.yaml", SPEC)
        write(tmp_path, "src/pedidos/a.py", "x = 1\n")
        commit(tmp_path, "base")
        args += ["--base", "HEAD"]
    else:
        make(tmp_path, "def test_ac_001_x(): pass\n")
    evidence = {"check": "AC-001", "diff": "AC-001", "mutate": "AC-001",
                "eval": "EVAL-001", "arch": "ARCH-001"}[command]
    write(tmp_path, "specs/constitution.yaml", yaml.safe_dump(constitution(f"kit:{command}", evidence)))
    if command == "arch":
        write(tmp_path, "specs/architecture.yaml", yaml.safe_dump({"rules": [
            {"id": "ARCH-001", "description": "sem rede", "from": ["t/*.py"], "forbid": ["httpx"]}]}))
    r = runner.invoke(app, args)
    assert r.exit_code == 0, r.output
    data = json.loads((tmp_path / f".sdd/{filename}.json").read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else [data]
    for row in rows:
        assert row["tool_version"] == __version__
        assert row["report_version"] == 1
        assert row["command"] == command
        assert row["constitution"][0]["status"] == "APROVADO"
        assert row["constitution"][1]["status"] == (
            "PENDENTE" if command in ("diff", "mutate") else "APROVADO")
        if command == "mutate":
            assert row["scope"]["max_mutants"] == 50
    md = (tmp_path / f".sdd/{filename}.md").read_text(encoding="utf-8")
    assert f"sdd-kit {__version__}" in md and "formato 1" in md and f"`{command}`" in md


def test_ac_038_evidencia_de_juiz_llm_explicitamente_probabilistica(tmp_path):
    eval_project(tmp_path, ev_with(judge="llm"), allow_llm=True)
    r = runner.invoke(app, ["eval", "-C", str(tmp_path)])
    assert r.exit_code == 0, r.output
    data = json.loads((tmp_path / ".sdd/eval.json").read_text(encoding="utf-8"))
    assert data["probabilistic"] is True
    md = (tmp_path / ".sdd/eval.md").read_text(encoding="utf-8")
    assert "Resultado: APROVADO (evidência probabilística)" in md


def test_ac_092_specs_do_kit_atribuem_uma_feature_por_arquivo():
    root = Path(__file__).resolve().parents[1]
    proj = core.load(root)
    assert not proj.errors, proj.errors
    from sdd.diff import matches

    assert len(proj.specs) > 1
    for file in (root / "src/sdd").rglob("*"):
        if file.suffix not in (".py", ".yaml"):
            continue
        rel = file.relative_to(root).as_posix()
        owners = [s.feature for s in proj.specs.values() if matches(rel, s.paths)]
        assert len(owners) == 1, (rel, owners)
