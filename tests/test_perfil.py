"""Perfil de agentes: matriz de módulos, cobertura, requisitos críticos, estágio e limites."""
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from sdd import core
from sdd.cli import app
from sdd.profile import catalog

runner = CliRunner()
PY = sys.executable
NUCLEO = [r.id for r in catalog().modules["N"].requirements]


def init(root: Path) -> Path:
    assert runner.invoke(app, ["init", "--profile", "agentes", "-C", str(root)]).exit_code == 0
    return root


def write_agents(root: Path, modules=None, coverage=None, stage="local"):
    cov = {rid: ["AC-001"] for rid in NUCLEO}
    cov.update({"N-04": ["AC-001"], "N-11": ["AC-001"]})
    cov.update(coverage or {})
    mods = {k: {"status": "inativo", "reason": "fora do escopo do teste"} for k in catalog().modules}
    mods["N"] = "ativo"
    mods.update(modules or {})
    (root / "specs/agents.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(
        {"profile": "agentes", "stage": stage, "modules": mods, "coverage": cov}, allow_unicode=True))


def set_test_command(root: Path):
    """Via YAML, não por troca de texto: o caminho do Python no Windows tem barras invertidas."""
    cfg_file = root / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg["tests"]["command"] = f"{PY} -m pytest -q -p no:cacheprovider --junitxml=.sdd/junit.xml t"
    cfg_file.write_text(encoding="utf-8", data=yaml.safe_dump(cfg, allow_unicode=True))


def errors(root: Path) -> str:
    return "\n".join(core.load(root).errors)


def warnings(root: Path) -> str:
    return "\n".join(core.load(root).warnings)


# --- REQ-015: perfil de agentes ---------------------------------------------------

def test_ac_063_init_com_perfil_cria_matriz_e_cobra_o_nucleo(tmp_path):
    init(tmp_path)
    prof = yaml.safe_load((tmp_path / "specs/agents.yaml").read_text(encoding="utf-8"))
    assert prof["modules"]["N"] == "ativo"
    assert set(prof["modules"]) == set(catalog().modules) and "L" in prof["modules"]
    assert all(v == "pendente" for k, v in prof["modules"].items() if k != "N")
    e = errors(tmp_path)
    assert all(f"{rid} (" in e and "sem evidência" in e for rid in NUCLEO)
    assert "Perfil de agentes" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")


def test_ac_063_matriz_completa_valida(tmp_path):
    init(tmp_path)
    write_agents(tmp_path)
    assert errors(tmp_path) == ""


def test_ac_064_pendente_e_aviso_em_local_e_erro_em_piloto(tmp_path):
    init(tmp_path)
    write_agents(tmp_path, modules={"M": "pendente"})
    assert errors(tmp_path) == "" and "módulo M (Memória) pendente" in warnings(tmp_path)
    write_agents(tmp_path, modules={"M": "pendente"}, stage="piloto")
    assert "módulo M (Memória) pendente" in errors(tmp_path)


def test_ac_064_modulo_nao_declarado(tmp_path):
    init(tmp_path)
    write_agents(tmp_path)
    prof = yaml.safe_load((tmp_path / "specs/agents.yaml").read_text(encoding="utf-8"))
    prof["modules"].pop("X")
    (tmp_path / "specs/agents.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(prof))
    assert "módulo X" in warnings(tmp_path)
    prof["modules"].pop("N")
    (tmp_path / "specs/agents.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(prof))
    assert "módulo N (Núcleo) não declarado" in errors(tmp_path)


def test_ac_065_cobertura_de_modulo_ativo(tmp_path):
    init(tmp_path)
    write_agents(tmp_path, modules={"R": "ativo"})
    e = errors(tmp_path)
    assert "R-01 (Procedência) sem evidência" in e and "R-04" in e
    write_agents(tmp_path, modules={"R": "ativo"}, coverage={
        "R-01": ["AC-001"], "R-02": ["AC-404"], "R-03": {"not_applicable": "índice somente leitura, sem revogação"},
        "R-04": ["NFR-001"]})
    e = errors(tmp_path)
    assert "R-02 (Acesso na recuperação) cita 'AC-404'" in e and "R-03" not in e and "R-01" not in e


def test_ac_065_inativo_exige_motivo_e_nucleo_nao_desativa(tmp_path):
    init(tmp_path)
    write_agents(tmp_path, modules={"C": "inativo", "N": {"status": "inativo", "reason": "x"}})
    e = errors(tmp_path)
    assert "módulo C inativo precisa de motivo" in e
    assert "módulo N (Núcleo) é obrigatório" in e


def test_ac_065_referencias_invalidas_no_arquivo(tmp_path):
    init(tmp_path)
    write_agents(tmp_path, modules={"Z": "ativo"}, coverage={"Q-99": ["AC-001"]})
    e = errors(tmp_path)
    assert "módulo 'Z' não existe" in e and "requisito 'Q-99' que não existe" in e


def test_ac_066_critico_exige_evidencia_deterministica(tmp_path):
    init(tmp_path)
    eval_ds = tmp_path / "evals/d.jsonl"
    eval_ds.parent.mkdir()
    eval_ds.write_text(encoding="utf-8", data='{"id": "c1"}\n')
    spec = tmp_path / "specs/features/FEATURE-001/spec.yaml"
    s = yaml.safe_load(spec.read_text(encoding="utf-8"))
    s["evals"] = [{"id": "EVAL-001", "metric": "m", "dataset": "evals/d.jsonl", "min_cases": 1,
                   "threshold": {"min": 0.9}}]
    s["tasks"][0]["origin"].append("EVAL-001")  # todo eval precisa de tarefa (requisito órfão)
    spec.write_text(encoding="utf-8", data=yaml.safe_dump(s, allow_unicode=True))
    write_agents(tmp_path, coverage={"N-04": ["EVAL-001"]})
    assert "N-04 (Confiança) é crítico: exige ao menos uma evidência determinística" in errors(tmp_path)
    write_agents(tmp_path, coverage={"N-04": ["EVAL-001", "AC-001"]})
    assert errors(tmp_path) == ""
    write_agents(tmp_path, coverage={"N-11": {"not_applicable": "sem credenciais"}})
    assert "N-11 (Segredos) é crítico e não aceita not_applicable" in errors(tmp_path)


def test_ac_067_producao_exige_modulo_p(tmp_path):
    init(tmp_path)
    write_agents(tmp_path, stage="producao")
    assert "estágio producao exige o módulo P" in errors(tmp_path)
    cov = {r.id: ["AC-001"] for r in catalog().modules["P"].requirements}
    write_agents(tmp_path, stage="producao", modules={"P": "ativo"}, coverage=cov)
    assert errors(tmp_path) == ""


def test_ac_068_check_mostra_a_matriz_com_estado_das_evidencias(tmp_path):
    init(tmp_path)
    write_agents(tmp_path, modules={"L": "ativo"}, coverage={
        r.id: ["AC-001"] for r in catalog().modules["L"].requirements})
    set_test_command(tmp_path)
    (tmp_path / "t").mkdir()
    (tmp_path / "t/test_x.py").write_text(encoding="utf-8",
                                          data="def test_ac_001(): pass\ndef test_nfr_001(): pass\n")
    r = runner.invoke(app, ["check", "-C", str(tmp_path)])
    assert r.exit_code == 0, r.output
    md = (tmp_path / ".sdd/report.md").read_text(encoding="utf-8")
    assert "## Perfil de agentes (estágio local)" in md
    assert "| N-04 Confiança * | COBERTO | AC-001 (OK) |" in md
    assert "| L-03 Direitos do titular * | COBERTO |" in md
    assert "Módulos fora do escopo:" in md and "A (inativo)" in md


def test_ac_068_falha_de_evidencia_aparece_na_matriz(tmp_path):
    init(tmp_path)
    write_agents(tmp_path)
    set_test_command(tmp_path)
    (tmp_path / "t").mkdir()
    (tmp_path / "t/test_x.py").write_text(encoding="utf-8",
                                          data="def test_ac_001(): assert False\ndef test_nfr_001(): pass\n")
    report = core.check(core.load(tmp_path))
    n04 = next(r for r in report["profile"]["requirements"] if r["id"] == "N-04")
    assert n04["state"] == "FALHA" and n04["evidence"] == [{"id": "AC-001", "verdict": "FALHOU"}]


def test_ac_069_design_exige_limites_com_perfil(tmp_path):
    init(tmp_path)
    write_agents(tmp_path)
    spec = tmp_path / "specs/features/FEATURE-001/spec.yaml"
    s = yaml.safe_load(spec.read_text(encoding="utf-8"))
    s["design"].pop("limits")
    spec.write_text(encoding="utf-8", data=yaml.safe_dump(s, allow_unicode=True))
    assert "design.limits é obrigatório" in errors(tmp_path)
    (tmp_path / "specs/agents.yaml").unlink()  # sem perfil, limites são opcionais
    assert errors(tmp_path) == ""


def test_limites_nao_aceitam_zero(tmp_path):
    from pydantic import ValidationError
    import pytest
    from sdd.models import Limits
    with pytest.raises(ValidationError):
        Limits(deadline_s=0, max_steps=1, max_tool_calls=0)
    Limits(deadline_s=1, max_steps=1, max_tool_calls=0)


def test_cli_profile_mostra_matriz_e_catalogo(tmp_path):
    init(tmp_path)
    write_agents(tmp_path)
    r = runner.invoke(app, ["profile", "-C", str(tmp_path)])
    assert r.exit_code == 0 and "N-04* DECLARADO" in r.output and "INATIVO" in r.output
    r = runner.invoke(app, ["profile", "--catalog"])
    assert "L — Proteção de dados e regulação (LGPD, PL 2338)" in r.output and "L-03*" in r.output
    r = runner.invoke(app, ["profile", "-C", str(tmp_path / "vazio")])
    assert r.exit_code == 2


def test_init_com_perfil_inexistente(tmp_path):
    r = runner.invoke(app, ["init", "--profile", "bancario", "-C", str(tmp_path)])
    assert r.exit_code == 2 and "perfil 'bancario' não existe" in r.stderr


def test_catalogo_e_consistente():
    cat = catalog()
    ids = [r.id for m in cat.modules.values() for r in m.requirements]
    assert len(ids) == len(set(ids))
    assert all(r.id.startswith(k + "-") for k, m in cat.modules.items() for r in m.requirements)
    assert [k for k, m in cat.modules.items() if m.mandatory] == ["N"]


# --- REQ-016: evals críticos e efeitos proibidos ----------------------------------------

def test_ac_071_eval_critico_reprova_com_um_caso(tmp_path):
    from test_evals import ev_with, lines_for, project as eval_project
    from sdd import evals
    eval_project(tmp_path, ev_with(critical=True, threshold={"min": 0.5}), plan=lines_for([1.0, 0.99, 1.0]))
    row = evals.run(core.load(tmp_path))["evals"][0]
    assert row["verdict"] == "FALHA_CRITICA" and "c99 (execução 2)" in row["detail"]


def test_ac_071_eval_critico_tudo_passando_aprova(tmp_path):
    from test_evals import ev_with, lines_for, project as eval_project
    from sdd import evals
    eval_project(tmp_path, ev_with(critical=True), plan=lines_for([1.0, 1.0, 1.0]))
    assert evals.run(core.load(tmp_path))["evals"][0]["verdict"] == "OK"


def test_ac_071_critico_lista_no_maximo_cinco_casos(tmp_path):
    from test_evals import ev_with, lines_for, project as eval_project
    from sdd import evals
    eval_project(tmp_path, ev_with(critical=True, threshold={"min": 0.1}), plan=lines_for([0.9, 0.9, 0.9]))
    detail = evals.run(core.load(tmp_path))["evals"][0]["detail"]
    assert detail.startswith("30 caso(s) falharam") and detail.endswith(" …") and detail.count("execução") == 5


def test_ac_072_efeitos_proibidos_aparecem_no_relatorio(tmp_path):
    from test_sdd import make
    make(tmp_path, "def test_ac_001(): pass\n")
    spec = tmp_path / "specs/features/FEATURE-001/spec.yaml"
    s = yaml.safe_load(spec.read_text(encoding="utf-8"))
    s["requirements"][0]["acceptance"][0]["forbidden"] = ["cobrar duas vezes", "enviar e-mail"]
    spec.write_text(encoding="utf-8", data=yaml.safe_dump(s, allow_unicode=True))
    report = core.check(core.load(tmp_path))
    assert report["criteria"][0]["text"] == "t — proibido: cobrar duas vezes; enviar e-mail"
