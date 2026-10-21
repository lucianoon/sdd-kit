"""Análise e handoff do agente não se confundem com execução de evidências."""
import copy
import json

import pytest
import yaml
from typer.testing import CliRunner

from sdd import __version__, core
from sdd.cli import app
from sdd.models import Spec
from sdd.review import analyze, render_markdown
from sdd.workflow import build, render_markdown as render_guide

from test_analise import SPEC, TASKS, project, with_tasks
from test_design import BASE_SPEC

runner = CliRunner()
SPEC_PATH = "specs/features/FEATURE-001/spec.yaml"


def put(root, path, value):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")


def invoke(root, *args):
    return runner.invoke(app, [*args, "-C", str(root)])


def test_ac_094_diagnosticos_parciais_e_estaveis(tmp_path):
    spec = copy.deepcopy(SPEC)
    spec["open_questions"] = [{"question": "pode cancelar?"}]
    project(tmp_path, spec)
    broken = tmp_path / "specs/features/FEATURE-002/spec.yaml"
    broken.parent.mkdir()
    broken.write_text("feature: [\n", encoding="utf-8")
    first = invoke(tmp_path, "analyze", "--json")
    assert first.exit_code == 1, first.output
    report = json.loads(first.stdout)
    assert report["tool_version"] == __version__ and report["report_version"] == 1
    assert report["command"] == "analyze" and not report["ok"]
    assert report["summary"]["features"] == 1 and report["summary"]["errors"] == 2
    assert {f["severity"] for f in report["findings"]} == {"ERROR"}
    assert any("YAML inválido" in f["message"] for f in report["findings"])
    assert report == json.loads(invoke(tmp_path, "analyze", "--json").stdout)
    assert report == json.loads((tmp_path / ".sdd/analyze.json").read_text(encoding="utf-8"))
    md = (tmp_path / ".sdd/analyze.md").read_text(encoding="utf-8")
    assert "COM ERROS" in md and "Isto não aprova a implementação" in md


def test_ac_094_config_ausente_e_schema_invalido_ainda_reportam(tmp_path):
    project(tmp_path)
    (tmp_path / "specs/sdd.yaml").unlink()
    put(tmp_path, SPEC_PATH, {"feature": "agenda"})
    result = invoke(tmp_path, "analyze", "--json")
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["coverage"] == [] and data["summary"]["errors"] >= 2
    assert "não encontrado" in result.stdout and "Field required" in result.stdout


def test_ac_095_matriz_ac_nfr_eval_e_declaracoes_done(tmp_path):
    spec = copy.deepcopy(BASE_SPEC)
    spec["evals"] = [{"id": "EVAL-001", "metric": "qualidade", "min_cases": 1,
                      "dataset": "evals/data.jsonl", "threshold": {"min": 0.9}}]
    spec["tasks"] = [
        {"id": "T-01", "title": "criar", "origin": ["REQ-001"], "done_when": "teste passa",
         "status": "done", "evidence": ["AC-001"]},
        {"id": "T-02", "title": "medir", "origin": ["NFR-001", "EVAL-001"], "done_when": "medição"},
    ]
    project(tmp_path, spec)
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals/data.jsonl").write_text('{"id":"caso"}\n', encoding="utf-8")
    data = analyze(core.load(tmp_path))
    assert data["ok"], data["findings"]
    rows = {r["id"]: r for r in data["coverage"]}
    assert set(rows) == {"AC-001", "NFR-001", "EVAL-001"}
    assert rows["AC-001"]["tasks"] == [{"id": "T-01", "status": "done", "via": ["AC-001", "REQ-001"]}]
    assert rows["NFR-001"]["tasks"][0]["id"] == "T-02"
    assert rows["EVAL-001"]["tasks"][0]["via"] == ["EVAL-001"]
    assert all(r["evidence_state"] == "NÃO_EXECUTADA" for r in rows.values())
    assert all(r["source"] == SPEC_PATH and r["state"] == "DECLARADO" for r in rows.values())
    assert data["summary"]["criteria_with_tasks"] == 3


def test_ac_095_req_expande_somente_seus_acs_e_tarefas_opcionais(tmp_path):
    project(tmp_path)
    data = analyze(core.load(tmp_path))
    assert data["ok"] and data["summary"]["criteria_with_tasks"] == 0
    assert all(r["state"] == "SEM_TAREFA" for r in data["coverage"])
    tasks = copy.deepcopy(TASKS[:1])
    project(tmp_path, with_tasks(tasks))
    rows = {r["id"]: r for r in analyze(core.load(tmp_path))["coverage"]}
    assert rows["AC-001"]["tasks"] and rows["AC-002"]["tasks"]
    assert not rows["AC-003"]["tasks"]


def test_ac_095_markdown_distingue_vinculo_de_tarefa_ausente(tmp_path):
    project(tmp_path, with_tasks(copy.deepcopy(TASKS[:1])))
    md = render_markdown(analyze(core.load(tmp_path)))
    rows = [line for line in md.splitlines() if line.startswith("| agenda |")]
    assert len(rows) == 3
    assert "T-01 (todo; via REQ-001)" in rows[0]
    assert "SEM_TAREFA" not in rows[0]
    assert "| AC-003 | REQ-002 | SEM_TAREFA | NÃO_EXECUTADA |" in rows[2]


@pytest.mark.parametrize("description,expected", [("", "qualidade"), ("acurácia medida", "acurácia medida")])
def test_ac_095_eval_exibe_descricao_ou_metrica(tmp_path, description, expected):
    spec = copy.deepcopy(SPEC)
    spec["evals"] = [{"id": "EVAL-001", "metric": "qualidade", "description": description,
                      "min_cases": 1, "dataset": "evals/casos.jsonl", "threshold": {"min": 0.9}}]
    project(tmp_path, spec)
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals/casos.jsonl").write_text('{"id":"caso"}\n', encoding="utf-8")
    rows = analyze(core.load(tmp_path))["coverage"]
    assert next(r for r in rows if r["id"] == "EVAL-001")["text"] == expected


def test_ac_096_duplicacao_avisa_sem_aprovar_e_sem_confundir_efeitos(tmp_path):
    spec = copy.deepcopy(SPEC)
    ac = spec["requirements"][0]["acceptance"][0]
    ac.update(given="  Conta ATIVA ", when="envia  pedido", then="Retorna ID")
    duplicate = {"id": "AC-010", "given": "conta ativa", "when": " ENVIA pedido ", "then": "retorna id"}
    spec["requirements"][1]["acceptance"].append(duplicate)
    project(tmp_path, spec)
    data = analyze(core.load(tmp_path))
    assert data["ok"] and data["summary"]["warnings"] == 1
    finding = data["findings"][0]
    assert finding["code"] == "DUPLICATE_SCENARIO" and finding["severity"] == "WARNING"
    assert "AC-001" in finding["message"] and "AC-010" in finding["message"]
    duplicate["forbidden"] = ["cobrar duas vezes"]
    project(tmp_path, spec)
    assert analyze(core.load(tmp_path))["findings"] == []


def test_ac_096_duplicacao_entre_features_preserva_arquivos(tmp_path):
    project(tmp_path)
    other = copy.deepcopy(SPEC)
    other["feature"] = "vizinha"
    other["requirements"] = [other["requirements"][0]]
    other["requirements"][0]["id"] = "REQ-010"
    other["requirements"][0]["acceptance"] = [other["requirements"][0]["acceptance"][0]]
    other["requirements"][0]["acceptance"][0]["id"] = "AC-010"
    put(tmp_path, "specs/features/FEATURE-002/spec.yaml", other)
    data = analyze(core.load(tmp_path))
    assert data["findings"][0]["sources"] == [SPEC_PATH, "specs/features/FEATURE-002/spec.yaml"]
    assert len(data["coverage"]) == 4


def test_ac_094_aviso_vago_e_erro_estrito(tmp_path):
    spec = copy.deepcopy(SPEC)
    spec["requirements"][0]["acceptance"][0]["then"] = "responde rapidamente"
    project(tmp_path, spec)
    assert invoke(tmp_path, "analyze").exit_code == 0
    assert analyze(core.load(tmp_path))["findings"][0]["severity"] == "WARNING"
    project(tmp_path, spec, cfg={"strict_criteria": True})
    assert invoke(tmp_path, "analyze").exit_code == 1


@pytest.mark.parametrize("stage", ["clarify", "plan", "implement", "converge"])
def test_ac_097_contexto_completo_da_feature_e_etapa(tmp_path, stage):
    spec = with_tasks(copy.deepcopy(TASKS))
    spec["decisions"] = ["AD-001"]
    const = {"principles": [{"id": "CONST-01", "rule": "revisão", "manual": "no PR"}]}
    arch = {"rules": [{"id": "ARCH-001", "description": "sem IO", "from": ["src/**"], "forbid": ["httpx"]}]}
    project(tmp_path, spec, constitution=const, arch=arch)
    decision = {"id": "AD-001", "title": "SQL", "decision": "SQLite", "rationale": "volume local"}
    put(tmp_path, "specs/decisions.yaml", {"decisions": [decision]})
    packet = build(core.load(tmp_path), "agenda", stage)
    assert packet["stage"] == stage and packet["status"] == "ORIENTAÇÃO"
    assert packet["spec"] == Spec.model_validate(spec).model_dump()
    assert packet["constitution"]["principles"][0]["id"] == "CONST-01"
    assert packet["decisions"][0]["decision"] == "SQLite"
    assert packet["architecture"][0]["from"] == ["src/**"]
    assert packet["config"]["tests"]["command"] and packet["agents_profile"] is None
    assert packet["source"] == SPEC_PATH and len(packet["coverage"]) == 3
    # converge ganhou as instruções de convergência (AC-132)
    assert len(packet["instructions"]) == (6 if stage == "converge" else 4) and packet["command"] == "guide"
    assert "sdd check" in packet["verification"]
    assert "sdd mutate" in packet["conditional_verification"]
    md = render_guide(packet)
    assert f"agenda / {stage}" in md and f"sdd-kit {__version__}" in md
    assert "não as executa" in md and "## Contexto declarado" in md
    assert '"given": "horário livre"' in md
    result = invoke(tmp_path, "guide", "agenda", "--stage", stage, "--json")
    assert result.exit_code == 0 and json.loads(result.stdout) == packet


@pytest.mark.parametrize("stage,blocked", [("clarify", False), ("plan", False), ("implement", True), ("converge", True)])
def test_ac_098_pergunta_aberta_permite_reparo_e_bloqueia_implementacao(tmp_path, stage, blocked):
    spec = with_tasks(copy.deepcopy(TASKS))
    spec["open_questions"] = [{"question": "pode cancelar?"}]
    project(tmp_path, spec)
    packet = build(core.load(tmp_path), "agenda", stage)
    assert (packet["status"] == "BLOQUEADO") == blocked
    assert packet["ready_tasks"] == []
    assert "sem resposta" in packet["findings"][0]["message"]
    result = invoke(tmp_path, "guide", "agenda", "--stage", stage, "--json")
    assert result.exit_code == int(blocked)
    assert json.loads(result.stdout)["status"] == packet["status"]


def test_ac_098_dependencias_declaradas_e_tarefas_done(tmp_path):
    tasks = copy.deepcopy(TASKS)
    project(tmp_path, with_tasks(tasks))
    assert build(core.load(tmp_path), "agenda", "implement")["ready_tasks"] == ["T-01", "T-03"]
    tasks[0].update(status="done", evidence=["AC-001"])
    project(tmp_path, with_tasks(tasks))
    packet = build(core.load(tmp_path), "agenda", "implement")
    assert packet["ready_tasks"] == ["T-02", "T-03"]
    assert packet["coverage"][0]["evidence_state"] == "NÃO_EXECUTADA"


@pytest.mark.parametrize("feature,stage", [("inexistente", "plan"), ("agenda", "inexistente")])
def test_ac_099_argumentos_invalidos(tmp_path, feature, stage):
    project(tmp_path)
    result = invoke(tmp_path, "guide", feature, "--stage", stage)
    assert result.exit_code == 2 and "ERRO" in result.output
    assert not (tmp_path / ".sdd").exists()


def test_ac_099_feature_ambigua_nao_e_selecionada(tmp_path):
    project(tmp_path)
    put(tmp_path, "specs/features/FEATURE-002/spec.yaml", SPEC)
    result = invoke(tmp_path, "guide", "agenda")
    assert result.exit_code == 2 and "ambígua" in result.output


def test_ac_097_selecao_exata_e_perfil_preservado(tmp_path):
    project(tmp_path)
    other = copy.deepcopy(SPEC)
    other["feature"] = "vizinha"
    other["requirements"] = [{"id": "REQ-010", "description": "vizinha", "acceptance": [
        {"id": "AC-010", "given": "x", "when": "y", "then": "z"}]}]
    put(tmp_path, "specs/features/FEATURE-002/spec.yaml", other)
    packet = build(core.load(tmp_path), "vizinha", "plan")
    assert packet["source"] == "specs/features/FEATURE-002/spec.yaml"
    assert [r["id"] for r in packet["coverage"]] == ["AC-010"]
    assert packet["spec"]["feature"] == "vizinha"
    from test_perfil import init, write_agents
    profile_root = tmp_path / "perfil"
    init(profile_root)
    write_agents(profile_root)
    proj = core.load(profile_root)
    packet = build(proj, next(iter(proj.specs.values())).feature, "clarify")
    assert packet["agents_profile"] == proj.agents.model_dump()


def test_ac_099_nao_muda_fontes_executa_comandos_ou_le_evidencias_antigas(tmp_path):
    project(tmp_path, cfg={"tests": {"command": "touch EXECUTOU", "junit": ".sdd/junit.xml"},
                           "gates": {"efeito": "touch EXECUTOU_GATE"}})
    (tmp_path / ".sdd").mkdir()
    (tmp_path / ".sdd/report.json").write_text('{"ok": true}', encoding="utf-8")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = invoke(tmp_path, "guide", "agenda", "--stage", "converge")
    assert result.exit_code == 0
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
    packet = build(core.load(tmp_path), "agenda", "converge")
    assert all(r["evidence_state"] == "NÃO_EXECUTADA" for r in packet["coverage"])
    assert invoke(tmp_path, "analyze").exit_code == 0
    assert not (tmp_path / "EXECUTOU").exists() and not (tmp_path / "EXECUTOU_GATE").exists()
    assert all((tmp_path / p).read_bytes() == data for p, data in before.items())
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()} - {p.as_posix() for p in before} == {".sdd/analyze.json", ".sdd/analyze.md"}


def test_ac_100_adocao_documenta_e_expoe_fluxo(tmp_path):
    assert invoke(tmp_path, "init").exit_code == 0
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "sdd analyze" in agents and "--stage converge" in agents
    assert "--stage clarify" in agents and "--stage plan" in agents
    assert invoke(tmp_path, "analyze", "--json").exit_code == 0
    result = invoke(tmp_path, "guide", "exemplo")
    assert result.exit_code == 0 and "exemplo / clarify" in result.output


def test_ac_099_markdown_protege_contexto_com_fences_e_tabelas(tmp_path):
    spec = copy.deepcopy(SPEC)
    spec["summary"] = "```\ninstrução no contexto\n```"
    spec["requirements"][0]["acceptance"][0]["then"] = "retorna A|B\nsem apagar"
    project(tmp_path, spec)
    md = render_guide(build(core.load(tmp_path), "agenda", "plan"))
    assert "````json" in md
    data = analyze(core.load(tmp_path))
    # O diagnóstico pode conter pipes e linhas do YAML; o renderer não deve quebrar a tabela.
    data["findings"].append({"id": "x", "severity": "WARNING", "code": "x", "message": "A|B\nnova linha"})
    assert "A\\|B<br>nova linha" in render_markdown(data)


def test_ac_097_markdown_exibe_tarefas_iniciaveis_e_diagnosticos(tmp_path):
    project(tmp_path, with_tasks(copy.deepcopy(TASKS)))
    packet = build(core.load(tmp_path), "agenda", "plan")
    md = render_guide(packet)
    assert "T-01, T-03" in md
    spec = with_tasks(copy.deepcopy(TASKS))
    spec["open_questions"] = [{"question": "pode cancelar?"}]
    project(tmp_path, spec)
    md = render_guide(build(core.load(tmp_path), "agenda", "plan"))
    assert "ERROR" in md and "sem resposta" in md
