"""Regressões de contratos, limites de IO e separação entre dados e execução."""
import copy
import json
import os
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from sdd import core, evals
from sdd.artifacts import ArtifactError, atomic_write, confined, load_yaml
from sdd.cli import app
from sdd.models import CostCeiling, Eval, Number, Threshold
from sdd.project import Project, load
from sdd.report import write_command_report

from test_analise import SPEC, project
from test_evals import project as eval_project, ev_with
from test_mutation import project as mutation_project, FORTE

runner = CliRunner()


def symlink(link, target, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"symlink não disponível nesta plataforma: {exc}")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["min", "max"])
def test_ac_103_thresholds_finitos(value, field):
    with pytest.raises(ValidationError):
        Threshold(**{field: value})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_ac_103_nfr_custo_e_variacao_finitos(value):
    with pytest.raises(ValidationError):
        Number(metric="latencia", max=value, unit="ms", source="PO")
    with pytest.raises(ValidationError):
        CostCeiling(value=value, unit="USD", window="execução")
    with pytest.raises(ValidationError):
        Eval(**ev_with(max_run_spread=value))


@pytest.mark.parametrize("rel", ["specs/sdd.yaml", "specs/features/FEATURE-001/spec.yaml", "specs/decisions.yaml",
                                  "specs/constitution.yaml", "specs/agents.yaml", "specs/architecture.yaml"])
def test_ac_104_arquivo_utf8_invalido_vira_diagnostico(tmp_path, rel):
    project(tmp_path)
    path = tmp_path / rel
    path.write_bytes(b"\xff\xfe\x80")
    proj = load(tmp_path)
    assert proj.errors and any(rel in e for e in proj.errors)


def test_ac_104_chave_yaml_duplicada_reprova(tmp_path):
    project(tmp_path)
    cfg = tmp_path / "specs/sdd.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "require_tasks: true\nrequire_tasks: false\n", encoding="utf-8")
    errors = load(tmp_path).errors
    assert any("chave YAML duplicada" in e and "require_tasks" in e for e in errors)


def test_ac_104_falha_de_io_vira_diagnostico(tmp_path):
    project(tmp_path)
    path = tmp_path / "specs/sdd.yaml"
    path.unlink()
    path.mkdir()
    assert any("specs/sdd.yaml" in e for e in load(tmp_path).errors)


def test_ac_104_yaml_merge_permite_override_explicito(tmp_path):
    path = tmp_path / "merge.yaml"
    path.write_text("base: &b {max: 10}\nlimite: {<<: *b, max: 20}\n", encoding="utf-8")
    assert load_yaml(path)["limite"] == {"max": 20}


def test_ac_104_specify_nao_cria_feature_com_config_ambigua(tmp_path):
    project(tmp_path)
    (tmp_path / "specs/sdd.yaml").write_text("require_design: true\nrequire_design: false\n", encoding="utf-8")
    result = runner.invoke(app, ["specify", "nova", "-C", str(tmp_path)])
    assert result.exit_code == 2 and "duplicada" in result.output
    assert not (tmp_path / "specs/features/FEATURE-002").exists()


def test_ac_105_core_preserva_interface_e_nao_executa_invalido(tmp_path):
    assert core.Project is Project and core.load is load
    project(tmp_path, cfg={"tests": {"command": "touch EXECUTOU", "junit": ".sdd/junit.xml"}})
    spec = tmp_path / "specs/features/FEATURE-001/spec.yaml"
    spec.write_text(spec.read_text(encoding="utf-8") + "desconhecido: true\n", encoding="utf-8")
    proj = load(tmp_path)
    report = core.check(proj)
    assert not report["ok"] and report["problems"] == proj.errors
    assert report["tests"]["exit_code"] is None and not (tmp_path / "EXECUTOU").exists()


@pytest.mark.parametrize("raw", [
    '{"case":"c0","run":1,"pass":false,"pass":true}',
    '{"case":"c0","run":true,"pass":true}',
    '{"case":"c0","run":1.5,"pass":true}',
    '{"case":"c0","run":"1","pass":true}',
    '{"case":"c0","run":0,"pass":true}',
    '{"case":"c0","run":-1,"pass":true}',
    '{"case":"c0","run":Infinity,"pass":true}',
])
def test_ac_106_resultados_ambiguos_nao_aprovam(tmp_path, raw):
    path = tmp_path / "results.jsonl"
    path.write_text(raw + "\n", encoding="utf-8")
    row = evals.evaluate("agente", Eval(**ev_with(min_cases=1, runs=1)), {"c0"}, path)
    assert row["verdict"] == "INCOMPLETO" and "linha 1" in row["detail"]


def test_ac_106_resultado_utf8_invalido(tmp_path):
    path = tmp_path / "results.jsonl"
    path.write_bytes(b"\xff")
    assert evals.evaluate("agente", Eval(**ev_with()), {"c0"}, path)["verdict"] == "INCOMPLETO"


def test_ac_107_mutacao_nao_escreve_em_symlink_externo(tmp_path):
    from sdd.mutation import run_feature
    root = tmp_path / "repo"
    mutation_project(root, FORTE)
    proj = load(root)
    spec = next(iter(proj.specs.values()))
    source = next((root / "src").rglob("*.py"))
    original = source.read_bytes()
    outside = tmp_path / "externo.py"
    outside.write_bytes(original)
    source.unlink()
    symlink(source, outside)
    report = run_feature(proj, spec)
    assert not report.ok and "fora da cópia" in report.error
    assert outside.read_bytes() == original and source.is_symlink()


def test_ac_107_restauracao_recusa_link_criado_pelos_testes(tmp_path):
    from sdd.mutation import run_feature
    root = tmp_path / "repo"
    mutation_project(root, FORTE)
    outside = tmp_path / "sentinela"
    outside.write_text("preservar", encoding="utf-8")
    probe = root / "probe"
    symlink(probe, outside)
    probe.unlink()
    source = next((root / "src").rglob("*.py")).relative_to(root).as_posix()
    (root / "runner.py").write_text(
        "from pathlib import Path\n"
        "counter = Path('counter')\n"
        "if counter.exists():\n"
        f"    target = Path({source!r})\n"
        "    target.unlink()\n"
        f"    target.symlink_to({str(outside)!r})\n"
        "else:\n"
        "    counter.write_text('1', encoding='utf-8')\n", encoding="utf-8")
    proj = load(root)
    proj.config.mutation.command = f'"{sys.executable}" runner.py'
    rep = run_feature(proj, next(iter(proj.specs.values())), max_mutants=1)
    assert not rep.ok and rep.error
    assert outside.read_text(encoding="utf-8") == "preservar"


@pytest.mark.parametrize("destination", ["analyze.json", "analyze.md", ".sdd"])
@pytest.mark.parametrize("invalid", [False, True])
def test_ac_111_analyze_nao_segue_symlinks(tmp_path, destination, invalid):
    root = tmp_path / "repo"
    project(root)
    outside = tmp_path / "externo"
    outside.mkdir()
    sentinel = outside / "sentinela"
    sentinel.write_text("preservar", encoding="utf-8")
    if destination == ".sdd":
        symlink(root / ".sdd", outside, directory=True)
    else:
        (root / ".sdd").mkdir()
        symlink(root / ".sdd" / destination, sentinel)
    if invalid:
        (root / "specs/sdd.yaml").write_text("invalido: true", encoding="utf-8")
    result = runner.invoke(app, ["analyze", "--json", "-C", str(root)])
    assert result.exit_code == 2 and "ERRO" in result.output
    assert sentinel.read_text(encoding="utf-8") == "preservar"
    assert sorted(p.name for p in outside.iterdir()) == ["sentinela"]


def test_ac_111_gravacao_atomica_utf8_e_json_estrito(tmp_path):
    atomic_write(tmp_path, ".sdd/a.md", "antes")
    atomic_write(tmp_path, ".sdd/a.md", "ação concluída")
    assert (tmp_path / ".sdd/a.md").read_text(encoding="utf-8") == "ação concluída"
    assert sorted(p.name for p in (tmp_path / ".sdd").iterdir()) == ["a.md"]
    with pytest.raises(ValueError):
        write_command_report(tmp_path, "nan", {"valor": float("nan")}, "inválido")
    assert not (tmp_path / ".sdd/nan.json").exists()


def test_ac_111_caminhos_recusam_links_internos_tambem(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    symlink(tmp_path / "link", target, directory=True)
    with pytest.raises(ArtifactError):
        confined(tmp_path, "link/relatorio.md")


def test_ac_111_fallback_sem_dir_fd_preserva_gravacao_atomica(tmp_path, monkeypatch):
    real_open = os.open

    def open_without_dir_fd(path, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is not None:
            raise NotImplementedError("plataforma sem dir_fd")
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "supports_dir_fd", set())
    monkeypatch.setattr(os, "open", open_without_dir_fd)
    for text in ("antes", "ação concluída"):
        atomic_write(tmp_path, ".sdd/sub/relatorio.md", text)
    assert (tmp_path / ".sdd/sub/relatorio.md").read_text(encoding="utf-8") == "ação concluída"
    assert list((tmp_path / ".sdd/sub").iterdir()) == [tmp_path / ".sdd/sub/relatorio.md"]


def test_ac_111_compatibilidade_sem_is_junction(tmp_path, monkeypatch):
    monkeypatch.delattr(Path, "is_junction", raising=False)
    assert confined(tmp_path, ".sdd/normal.md") == tmp_path / ".sdd/normal.md"


def test_ac_111_enable_nao_edita_config_por_link(tmp_path):
    project(tmp_path)
    cfg = tmp_path / "specs/sdd.yaml"
    outside = tmp_path.parent / (tmp_path.name + "-externo.yaml")
    original = cfg.read_bytes()
    outside.write_bytes(original)
    cfg.unlink()
    symlink(cfg, outside)
    result = runner.invoke(app, ["enable", "design", "-C", str(tmp_path)])
    assert result.exit_code == 2
    assert outside.read_bytes() == original


@pytest.mark.parametrize("directory", [".", "..", "../externo", "/tmp/externo", "C:/externo", "src", "src/resultados", "specs", "evals"])
def test_ac_112_nao_apaga_fontes_nem_roda_harness(tmp_path, directory):
    root = tmp_path / "repo"
    eval_project(root)
    cfg_path = root / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["evals"].update(results_dir=directory, command="touch EXECUTOU")
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    sentinel = root / "src/sentinela.py"
    sentinel.parent.mkdir()
    sentinel.write_text("preservar", encoding="utf-8")
    proj = load(root)
    if not proj.errors:
        report = evals.run(proj)
        assert not report["ok"] and report["harness"] is None
    assert sentinel.read_text(encoding="utf-8") == "preservar"
    assert not (root / "EXECUTOU").exists() and (root / "evals/tools.jsonl").exists()


def test_ac_112_resultados_normais_preservam_arquivos_vizinhos(tmp_path):
    eval_project(tmp_path)
    out = tmp_path / ".sdd/evals"
    out.mkdir(parents=True)
    (out / "LEIAME.md").write_text("preservar", encoding="utf-8")
    assert evals.run(load(tmp_path))["ok"]
    assert (out / "LEIAME.md").read_text(encoding="utf-8") == "preservar"


def test_ac_112_resultados_customizados_permitem_reexecucao(tmp_path):
    eval_project(tmp_path)
    config = tmp_path / "specs/sdd.yaml"
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    cfg["evals"]["results_dir"] = "resultados"
    config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    harness = tmp_path / "harness.py"
    harness.write_text(harness.read_text(encoding="utf-8").replace(".sdd/evals", "resultados"), encoding="utf-8")
    assert evals.run(load(tmp_path))["ok"]
    out = tmp_path / "resultados"
    (out / "LEIAME.md").write_text("preservar", encoding="utf-8")
    report = evals.run(load(tmp_path))
    assert report["ok"], report["problems"]
    assert (out / "LEIAME.md").read_text(encoding="utf-8") == "preservar"
