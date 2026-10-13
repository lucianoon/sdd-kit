"""sdd specify: esqueleto de spec com IDs livres e seções exigidas pelo size."""
import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from sdd import core
from sdd.cli import app

runner = CliRunner()


def init(root: Path) -> Path:
    assert runner.invoke(app, ["init", "-C", str(root)]).exit_code == 0
    return root


def specify(root: Path, *args: str):
    return runner.invoke(app, ["specify", *args, "-C", str(root)])


def fill(text: str) -> str:
    """Simula quem preenche o esqueleto: troca cada marcador por conteúdo real."""
    text = re.sub(r'"PREENCHER: ex\. src/([\w-]+)/\*\*"', r'"src/\1/**"', text)
    text = re.sub(r"(\s+max:) 0\s+# PREENCHER.*", r"\1 200", text)
    text = re.sub(r"\s+# PREENCHER.*", "", text)
    text = re.sub(r'"PREENCHER: ([^"]*)"', lambda m: '"' + m.group(1).split(",")[0].split("|")[0].strip() + '"', text)
    text = text.replace('via: "http"', "via: http")
    return text


def test_ac_061_ids_livres_em_todo_o_projeto(tmp_path):
    init(tmp_path)  # o exemplo do init já usa REQ-001, AC-001 e NFR-001
    r = specify(tmp_path, "criar-pedido", "--size", "large", "--acs", "2")
    assert r.exit_code == 0, r.output
    assert "REQ: REQ-002  AC: AC-002, AC-003  NFR: NFR-002" in r.output
    r = specify(tmp_path, "cancelar-pedido")
    assert "REQ: REQ-003  AC: AC-004" in r.output and "NFR" not in r.output
    assert (tmp_path / "specs/features/FEATURE-003/spec.yaml").exists()


def test_ac_061_size_define_as_secoes(tmp_path):
    init(tmp_path)
    specify(tmp_path, "grande", "--size", "complex")
    specify(tmp_path, "pequena", "--size", "small")
    grande = yaml.safe_load((tmp_path / "specs/features/FEATURE-002/spec.yaml").read_text(encoding="utf-8"))
    pequena = yaml.safe_load((tmp_path / "specs/features/FEATURE-003/spec.yaml").read_text(encoding="utf-8"))
    assert "design" in grande and grande["design"]["dependencies"] == []
    assert "design" not in pequena


def test_ac_062_esqueleto_nao_passa_ate_ser_preenchido(tmp_path):
    init(tmp_path)
    specify(tmp_path, "criar-pedido", "--size", "large")
    errors = core.load(tmp_path).errors
    assert errors and all("PREENCHER" in e for e in errors)
    assert any(e.startswith("specs/features/FEATURE-002/spec.yaml:4:") for e in errors)  # aponta a linha


def test_ac_062_esqueleto_preenchido_valida(tmp_path):
    init(tmp_path)
    specify(tmp_path, "criar-pedido", "--size", "large", "--acs", "2")
    f = tmp_path / "specs/features/FEATURE-002/spec.yaml"
    f.write_text(encoding="utf-8", data=fill(f.read_text(encoding="utf-8")))
    assert "PREENCHER" not in f.read_text(encoding="utf-8")
    assert core.load(tmp_path).errors == []


def test_specify_recusa_nome_invalido_ou_repetido(tmp_path):
    init(tmp_path)
    assert specify(tmp_path, "Nome_Ruim").exit_code == 2
    assert specify(tmp_path, "exemplo").exit_code == 2  # já existe no init
    assert specify(tmp_path, "x", "--size", "enorme").exit_code == 2
    assert specify(tmp_path, "x", "--acs", "0").exit_code == 2


def test_specify_funciona_com_outra_spec_ainda_invalida(tmp_path):
    init(tmp_path)
    specify(tmp_path, "primeira", "--size", "large")  # incompleta: não valida
    r = specify(tmp_path, "segunda")
    assert r.exit_code == 0 and "REQ: REQ-003" in r.output


def test_specify_em_projeto_sem_specs(tmp_path):
    r = specify(tmp_path, "primeira")
    assert r.exit_code == 0 and "REQ: REQ-001  AC: AC-001" in r.output


def test_ac_062_palavra_em_prosa_nao_conta_como_marcador(tmp_path):
    init(tmp_path)
    f = tmp_path / "specs/features/FEATURE-001/spec.yaml"
    f.write_text(encoding="utf-8", data=f.read_text(encoding="utf-8").replace(
        "summary: Substitua por uma feature real.", "summary: o marcador PREENCHER é tratado pelo validador"))
    assert core.load(tmp_path).errors == []
