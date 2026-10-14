"""Tarefas, constituição executável, critério vago e SDD-Fix."""
import copy
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from sdd import core
from sdd.analysis import vague_terms
from sdd.cli import app
from sdd.models import Task

from test_diff import commit, git, write

runner = CliRunner()
PY = sys.executable

SPEC = {
    "feature": "agenda", "version": 1, "size": "medium",
    "requirements": [
        {"id": "REQ-001", "description": "reservar",
         "acceptance": [{"id": "AC-001", "given": "horário livre", "when": "confirma", "then": "cria reserva"},
                        {"id": "AC-002", "given": "duas confirmações", "when": "concorrentes",
                         "then": "uma única reserva"}]},
        {"id": "REQ-002", "description": "consultar",
         "acceptance": [{"id": "AC-003", "given": "agenda", "when": "consulta", "then": "lista horários"}]},
    ],
}
TASKS = [
    {"id": "T-01", "title": "persistir", "origin": ["REQ-001"], "done_when": "migração aplica"},
    {"id": "T-02", "title": "concorrência", "origin": ["AC-002"], "depends_on": ["T-01"],
     "done_when": "teste concorrente"},
    {"id": "T-03", "title": "consulta", "origin": ["REQ-002"], "done_when": "lista"},
]


def project(root: Path, spec: dict | None = None, cfg: dict | None = None, constitution=None, arch=None):
    (root / "specs/features/FEATURE-001").mkdir(parents=True, exist_ok=True)
    base_cfg = {"tests": {"command": f"{PY} -m pytest -q -p no:cacheprovider --junitxml=.sdd/junit.xml t",
                          "junit": ".sdd/junit.xml"}}
    base_cfg.update(cfg or {})
    (root / "specs/sdd.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(base_cfg, allow_unicode=True))
    (root / "specs/features/FEATURE-001/spec.yaml").write_text(
        encoding="utf-8", data=yaml.safe_dump(spec or SPEC, allow_unicode=True))
    if constitution is not None:
        (root / "specs/constitution.yaml").write_text(encoding="utf-8",
                                                      data=yaml.safe_dump(constitution, allow_unicode=True))
    if arch is not None:
        (root / "specs/architecture.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(arch))
    (root / "t").mkdir(exist_ok=True)
    (root / "t/test_x.py").write_text(encoding="utf-8", data=(
        "def test_ac_001(): pass\ndef test_ac_002(): pass\ndef test_ac_003(): pass\n"))
    return root


def with_tasks(tasks) -> dict:
    s = copy.deepcopy(SPEC)
    s["tasks"] = tasks
    return s


def errors(root: Path) -> str:
    return "\n".join(core.load(root).errors)


# --- REQ-017: tarefas ------------------------------------------------------------------

def test_ac_073_tarefas_validas(tmp_path):
    assert errors(project(tmp_path, with_tasks(TASKS))) == ""


def test_ac_073_origem_dependencia_e_duplicata_invalidas(tmp_path):
    bad = copy.deepcopy(TASKS)
    bad[0]["origin"] = ["AC-404"]
    bad[1]["depends_on"] = ["T-09"]
    bad.append({**TASKS[2], "evidence": ["AC-777"]})
    e = errors(project(tmp_path, with_tasks(bad)))
    assert "T-01 tem origem 'AC-404' inexistente" in e
    assert "T-02 depende de 'T-09'" in e
    assert "tarefa T-03 duplicada" in e and "evidência 'AC-777' inexistente" in e


def test_ac_073_origem_pode_ser_principio_ou_regra(tmp_path):
    t = copy.deepcopy(TASKS) + [{"id": "T-04", "title": "logs", "origin": ["CONST-01", "ARCH-001"],
                                 "done_when": "sem segredo em log"}]
    const = {"principles": [{"id": "CONST-01", "rule": "sem segredos em log", "manual": "revisão no PR"}]}
    arch = {"rules": [{"id": "ARCH-001", "description": "d", "from": ["src/**"], "forbid": ["x"]}]}
    project(tmp_path, with_tasks(t), constitution=const, arch=arch)
    assert errors(tmp_path) == ""


def test_ac_074_ciclo_de_dependencias(tmp_path):
    t = copy.deepcopy(TASKS)
    t[0]["depends_on"] = ["T-02"]
    e = errors(project(tmp_path, with_tasks(t)))
    assert "dependências em ciclo: T-01 → T-02 → T-01" in e
    t2 = copy.deepcopy(TASKS)
    t2[2]["depends_on"] = ["T-03"]
    assert "T-03 depende de si mesma" in errors(project(tmp_path / "b", with_tasks(t2)))


def test_ac_075_requisito_orfao(tmp_path):
    t = [x for x in copy.deepcopy(TASKS) if x["id"] != "T-03"]
    e = errors(project(tmp_path, with_tasks(t)))
    assert "AC-003 não é coberto por nenhuma tarefa (requisito órfão)" in e
    assert "AC-001" not in e  # coberto via REQ-001


def test_ac_075_nfr_e_eval_orfaos(tmp_path):
    from test_design import BASE_SPEC
    s = copy.deepcopy(BASE_SPEC)
    s["tasks"] = [{"id": "T-01", "title": "x", "origin": ["REQ-001"], "done_when": "x"}]
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals/d.jsonl").write_text(encoding="utf-8", data='{"id": "c"}\n')
    s["evals"] = [{"id": "EVAL-001", "metric": "m", "dataset": "evals/d.jsonl", "min_cases": 1,
                   "threshold": {"min": 0.5}}]
    e = errors(project(tmp_path, s))
    assert "NFR-001 não é coberto" in e and "EVAL-001 não é coberto" in e


def test_ac_076_concluida_exige_evidencia():
    with pytest.raises(ValidationError, match="precisa de `evidence`"):
        Task(id="T-01", title="x", origin=["AC-001"], done_when="x", status="done")


def test_ac_076_concluida_com_evidencia_falhando_reprova_o_check(tmp_path):
    t = copy.deepcopy(TASKS)
    t[1].update(status="done", evidence=["AC-002"])
    project(tmp_path, with_tasks(t))
    (tmp_path / "t/test_x.py").write_text(encoding="utf-8", data=(
        "def test_ac_001(): pass\ndef test_ac_002(): assert False\ndef test_ac_003(): pass\n"))
    report = core.check(core.load(tmp_path))
    assert any("T-02 (agenda) marcada como done, mas a evidência não passa: AC-002 FALHOU" in p
               for p in report["problems"])
    md = core.render_markdown(report)
    assert "## Tarefas" in md and "| agenda | T-02 concorrência | done | AC-002 | AC-002 (FALHOU) |" in md


def test_ac_077_tarefas_obrigatorias_por_size(tmp_path):
    s = copy.deepcopy(SPEC)
    s["size"] = "large"
    e = errors(project(tmp_path, s, cfg={"require_tasks": True}))
    assert "`tasks` obrigatório para size 'large'" in e
    s["size"] = "small"
    assert errors(project(tmp_path / "b", s, cfg={"require_tasks": True})) == ""


# --- REQ-018: constituição executável ----------------------------------------------------

def test_ac_078_principio_precisa_de_cobranca(tmp_path):
    project(tmp_path, constitution={"principles": [{"id": "CONST-01", "rule": "r"}]})
    assert "precisa de `enforced_by` ou de `manual`" in errors(tmp_path)


def test_ac_078_referencias_invalidas(tmp_path):
    const = {"principles": [
        {"id": "CONST-01", "rule": "r", "enforced_by": ["gate:inexistente", "kit:magia", "ARCH-009",
                                                         "AC-404", "profile:N-04", "profile:Z-99"]},
        {"id": "CONST-01", "rule": "duplicado", "manual": "x"},
    ]}
    e = errors(project(tmp_path, constitution=const))
    for msg in ("gate 'inexistente' não definido", "'kit:magia' não é recurso do kit",
                "regra 'ARCH-009' não existe", "'AC-404' não é AC, NFR, EVAL",
                "'profile:N-04' exige o perfil de agentes", "requisito 'Z-99' não existe",
                "princípio CONST-01 duplicado"):
        assert msg in e, msg


def test_ac_078_referencias_validas(tmp_path):
    const = {"principles": [
        {"id": "CONST-01", "rule": "toda execução tem limites", "enforced_by": ["kit:limits", "AC-001"]},
        {"id": "CONST-02", "rule": "sem segredos no código", "enforced_by": ["gate:segredos"]},
        {"id": "CONST-03", "rule": "nomes em português", "manual": "revisão no PR"},
    ]}
    project(tmp_path, constitution=const, cfg={"gates": {"segredos": f"{PY} -c \"pass\""}})
    assert errors(tmp_path) == ""


def test_ac_079_check_cobra_e_mostra_a_constituicao(tmp_path):
    const = {"principles": [
        {"id": "CONST-01", "rule": "reserva é única", "enforced_by": ["AC-002"]},
        {"id": "CONST-02", "rule": "sem segredos", "enforced_by": ["gate:segredos"]},
        {"id": "CONST-03", "rule": "nomes em português", "manual": "revisão no PR"},
    ]}
    project(tmp_path, constitution=const, cfg={"gates": {"segredos": f"{PY} -c \"raise SystemExit(1)\""}})
    report = core.check(core.load(tmp_path))
    assert not report["ok"] and "gate 'segredos' falhou (código 1)" in report["problems"]
    rows = {c["id"]: c for c in report["constitution"]}
    assert rows["CONST-01"]["status"] == "APROVADO"
    assert rows["CONST-02"]["status"] == "VIOLADO"
    assert rows["CONST-03"]["status"] == "MANUAL"
    md = core.render_markdown(report)
    assert "## Constituição" in md and "revisão manual: revisão no PR" in md


# --- REQ-019: critério vago ------------------------------------------------------------

@pytest.mark.parametrize("texto,vagos", [
    ("o agente responde corretamente", ["corretamente"]),
    ("a listagem é rápida e segura", ["rapida", "segura"]),
    ("lista em até 300 ms com 10 mil registros", []),          # tem número: mensurável
    ("cria reserva e retorna o identificador", []),
    ("aceita seguro-saúde como plano", []),                    # palavra composta não conta
    ("returns quickly", ["quickly"]),
])
def test_ac_080_termos_vagos(texto, vagos):
    assert vague_terms(texto) == vagos


def test_ac_080_aviso_ou_erro_conforme_config(tmp_path):
    s = copy.deepcopy(SPEC)
    s["requirements"][1]["acceptance"][0]["then"] = "lista horários rapidamente"
    proj = core.load(project(tmp_path, s))
    assert proj.errors == [] and any("AC-003: critério vago (rapidamente)" in w for w in proj.warnings)
    proj = core.load(project(tmp_path / "b", s, cfg={"strict_criteria": True}))
    assert any("AC-003: critério vago" in e for e in proj.errors)


# --- REQ-020: SDD-Fix ------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    s = copy.deepcopy(SPEC)
    s["paths"] = ["src/agenda/**"]
    write(tmp_path, "specs/sdd.yaml", "tests: {command: 'true', junit: x}\ncode: ['src/**']\n")
    write(tmp_path, "specs/features/FEATURE-001/spec.yaml", yaml.safe_dump(s, allow_unicode=True))
    write(tmp_path, "src/agenda/reserva.py", "x = 1\n")
    write(tmp_path, "tests/test_reserva.py", "def test_ac_002_unica(): pass\n")
    commit(tmp_path, "base")
    git(tmp_path, "checkout", "-qb", "pr")
    return tmp_path


def run_diff(root):
    return runner.invoke(app, ["diff", "-b", "main", "-C", str(root)])


def test_ac_081_correcao_com_teste_de_regressao_aprova(repo):
    write(repo, "src/agenda/reserva.py", "x = 2  # corrige corrida\n")
    write(repo, "tests/test_reserva.py", "def test_ac_002_unica(): pass\ndef test_ac_002_regressao_corrida(): pass\n")
    commit(repo, "fix: reserva duplicada sob concorrência\n\nSDD-Fix: AC-002")
    r = run_diff(repo)
    assert r.exit_code == 0, r.output
    assert "correção de AC-002 sem mudar a spec, com teste de regressão em tests/test_reserva.py" in r.output


def test_ac_082_correcao_sem_teste_reprova(repo):
    write(repo, "src/agenda/reserva.py", "x = 2\n")
    commit(repo, "fix: algo\n\nSDD-Fix: AC-002")
    r = run_diff(repo)
    assert r.exit_code == 1 and "SDD-Fix cita AC-002 sem teste de regressão" in r.stderr


def test_ac_082_teste_alterado_precisa_citar_o_id(repo):
    write(repo, "src/agenda/reserva.py", "x = 2\n")
    write(repo, "tests/test_outro.py", "def test_ac_001_outro(): pass\n")
    commit(repo, "fix: algo\n\nSDD-Fix: AC-002")
    assert run_diff(repo).exit_code == 1


def test_ac_082_id_inexistente_reprova(repo):
    write(repo, "src/agenda/reserva.py", "x = 2\n")
    write(repo, "tests/test_reserva.py", "def test_ac_099(): pass\n")
    commit(repo, "fix: algo\n\nSDD-Fix: AC-099")
    r = run_diff(repo)
    assert r.exit_code == 1 and "SDD-Fix cita AC-099, que não existe" in r.stderr


def test_ac_078_referencia_ao_perfil_exige_modulo_ativo(tmp_path):
    from test_perfil import init, write_agents
    init(tmp_path)
    write_agents(tmp_path)  # N ativo, demais inativos
    const = {"principles": [{"id": "CONST-01", "rule": "confiança", "enforced_by": ["profile:N-04"]}]}
    (tmp_path / "specs/constitution.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(const))
    assert errors(tmp_path) == ""
    const["principles"][0]["enforced_by"] = ["profile:R-01"]  # módulo R inativo
    (tmp_path / "specs/constitution.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(const))
    assert "'profile:R-01' exige o perfil de agentes com o módulo R ativo" in errors(tmp_path)
