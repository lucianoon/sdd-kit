"""Níveis de adoção: init --preset e sdd enable."""
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from sdd import __version__, core
from sdd.cli import app

runner = CliRunner()


def run(*args):
    return runner.invoke(app, list(args))


def files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_ac_083_init_minimo_e_leve(tmp_path):
    r = run("init", "-C", str(tmp_path))
    assert r.exit_code == 0, r.output
    assert files(tmp_path) == {"specs/sdd.yaml", "specs/features/FEATURE-001/spec.yaml", "AGENTS.md",
                               ".github/workflows/sdd.yml"}
    total = sum(len((tmp_path / f).read_text(encoding="utf-8").splitlines()) for f in files(tmp_path))
    assert total < 100
    spec = yaml.safe_load((tmp_path / "specs/features/FEATURE-001/spec.yaml").read_text(encoding="utf-8"))
    assert spec["size"] == "small" and "design" not in spec
    assert "<!-- sdd:" not in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert core.load(tmp_path).errors == []


@pytest.mark.parametrize("preset,esperados,ausentes", [
    ("padrao", {"specs/constitution.yaml", "specs/architecture.yaml", "specs/decisions.yaml"}, set()),
    ("completo", {"specs/constitution.yaml", "specs/architecture.yaml", "specs/decisions.yaml"}, set()),
])
def test_ac_084_presets_maiores_validam(tmp_path, preset, esperados, ausentes):
    assert run("init", "--preset", preset, "-C", str(tmp_path)).exit_code == 0
    assert esperados <= files(tmp_path)
    cfg = yaml.safe_load((tmp_path / "specs/sdd.yaml").read_text(encoding="utf-8"))
    assert cfg["require_design"] is True and cfg["require_tasks"] is True
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    for layer in ("design", "tasks", "constitution", "arch", "decisions"):
        assert f"<!-- sdd:{layer} -->" in agents
    workflow = (tmp_path / ".github/workflows/sdd.yml").read_text(encoding="utf-8")
    assert ("sdd mutate" in workflow) == (preset == "completo")
    assert cfg.get("strict_criteria", False) == (preset == "completo")
    assert core.load(tmp_path).errors == []


def test_ac_084_preset_inexistente(tmp_path):
    r = run("init", "--preset", "gigante", "-C", str(tmp_path))
    assert r.exit_code == 2 and "preset 'gigante' não existe" in r.stderr


def test_ac_085_enable_liga_camadas_num_projeto_minimo(tmp_path):
    run("init", "-C", str(tmp_path))
    r = run("enable", "design", "constitution", "mutate", "-C", str(tmp_path))
    assert r.exit_code == 0, r.output
    assert "criado   specs/constitution.yaml" in r.output
    cfg = yaml.safe_load((tmp_path / "specs/sdd.yaml").read_text(encoding="utf-8"))
    assert cfg["require_design"] is True and cfg["mutation"]["min_score"] == 0.8
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- sdd:design -->" in agents and "<!-- sdd:constitution -->" in agents
    assert "sdd mutate" in (tmp_path / ".github/workflows/sdd.yml").read_text(encoding="utf-8")
    assert core.load(tmp_path).errors == []


def test_ac_085_enable_e_idempotente(tmp_path):
    run("init", "-C", str(tmp_path))
    run("enable", "design", "agentes", "-C", str(tmp_path))
    before = {f: (tmp_path / f).read_text(encoding="utf-8") for f in files(tmp_path)}
    r = run("enable", "design", "agentes", "-C", str(tmp_path))
    assert r.exit_code == 0 and "mantido" in r.output
    assert {f: (tmp_path / f).read_text(encoding="utf-8") for f in files(tmp_path)} == before


def test_ac_085_enable_liga_flag_que_estava_desligada(tmp_path):
    run("init", "-C", str(tmp_path))
    cfg = tmp_path / "specs/sdd.yaml"
    cfg.write_text(encoding="utf-8", data=cfg.read_text(encoding="utf-8") + "strict_criteria: false\n")
    run("enable", "strict", "-C", str(tmp_path))
    text = cfg.read_text(encoding="utf-8")
    assert yaml.safe_load(text)["strict_criteria"] is True and text.count("strict_criteria") == 1


def test_ac_085_camada_inexistente(tmp_path):
    run("init", "-C", str(tmp_path))
    r = run("enable", "turbo", "-C", str(tmp_path))
    assert r.exit_code == 2 and "camada 'turbo' não existe" in r.stderr


def test_ac_086_init_nunca_sobrescreve(tmp_path):
    (tmp_path / "AGENTS.md").write_text(encoding="utf-8", data="meu conteúdo\n")
    r = run("init", "-C", str(tmp_path))
    assert "mantido  AGENTS.md" in r.output
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "meu conteúdo\n"


def test_versao():
    r = run("--version")
    assert r.exit_code == 0 and r.output.strip() == f"sdd-kit {__version__}"
