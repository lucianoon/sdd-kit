"""End-to-end contracts for agent integrations, reviewed evidence and spec lifecycle."""
import copy
import json

import pytest
import yaml
from typer.testing import CliRunner

from sdd import core
from sdd import changes
from sdd.adapters import import_spec, parse
from sdd.artifacts import ArtifactError, load_yaml
from sdd.integrations import install
from sdd.learning import (add_lesson, accept_lesson, adequacy, citation, context,
                          digest, lessons, save, template)
from sdd.cli import app
from sdd.workflow import build
from test_analise import SPEC, project

SPEC_PATH = "specs/features/FEATURE-001/spec.yaml"
runner = CliRunner()


def invoke(root, *args):
    return runner.invoke(app, [*args, "-C", str(root)])


def review(root):
    template(root, "agenda")
    path = "specs/reviews/agenda.yaml"
    value = load_yaml(root / path)
    value.update(implementer="author", reviewer="reviewer", reviewer_kind="agent")
    for item in value["items"]:
        item.update(verdict="adequate", assertion="consulta o estado persistido",
                    detects="retornar sucesso sem persistir", evidence=[citation(root, "t/test_x.py:1").model_dump()])
    save(root, path, value)
    return path, value


def test_ac_121_integracoes_idempotentes_e_customizacao_preservada(tmp_path):
    outputs = install(tmp_path, "all")
    assert len(outputs) == 12
    assert outputs == install(tmp_path, "all")
    for name in outputs:
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert "sdd guide <feature> --stage" in text and "sdd check" in text
    custom = tmp_path / ".cursor/commands/sdd-plan.md"
    custom.write_text("minhas regras", encoding="utf-8")
    with pytest.raises(ArtifactError, match="preservada"):
        install(tmp_path, "all")
    assert custom.read_text(encoding="utf-8") == "minhas regras"
    assert invoke(tmp_path, "integrate", "unknown").exit_code == 2


def test_ac_121_preflight_recusa_links_e_nao_instala_parcial(tmp_path):
    custom = tmp_path / ".claude/skills/sdd-plan/SKILL.md"
    custom.parent.mkdir(parents=True)
    custom.write_text("personalizado", encoding="utf-8")
    with pytest.raises(ArtifactError):
        install(tmp_path, "all")
    assert not (tmp_path / ".agents").exists()
    with pytest.raises(ArtifactError):
        install(tmp_path, "../escape")


def test_ac_122_adequacao_pendente_distincao_e_hashes(tmp_path):
    project(tmp_path)
    assert invoke(tmp_path, "adequacy", "template", "agenda").exit_code == 0
    assert invoke(tmp_path, "adequacy", "check", "agenda").exit_code == 1
    (tmp_path / "specs/reviews/agenda.yaml").unlink()
    path, value = review(tmp_path)
    report = adequacy(tmp_path, "agenda")
    assert report["ok"] and "não executa testes" in report["scope"]
    value["reviewer"] = "AUTHOR"
    save(tmp_path, path, value)
    assert not adequacy(tmp_path, "agenda")["ok"]
    value["reviewer"] = "reviewer"
    save(tmp_path, path, value)
    (tmp_path / "t/test_x.py").write_text("def test_ac_001(): assert False\n", encoding="utf-8")
    assert any("desatualizada" in p for p in adequacy(tmp_path, "agenda")["problems"])


def test_ac_122_criterios_duplicados_revisao_antiga_e_fontes(tmp_path):
    spec = copy.deepcopy(SPEC)
    spec["paths"] = ["t/*.py"]
    project(tmp_path, spec)
    path, value = review(tmp_path)
    assert adequacy(tmp_path, "agenda")["ok"]
    value["items"].append(value["items"][0])
    save(tmp_path, path, value)
    assert not adequacy(tmp_path, "agenda")["ok"]
    value["items"].pop()
    save(tmp_path, path, value)
    (tmp_path / "t/new.py").write_text("x = 1\n", encoding="utf-8")
    assert any("fontes" in p for p in adequacy(tmp_path, "agenda")["problems"])
    spec["summary"] = "nova intenção"
    save(tmp_path, SPEC_PATH, spec)
    assert any("spec alterada" in p for p in adequacy(tmp_path, "agenda")["problems"])
    with pytest.raises(ArtifactError):
        citation(tmp_path, "../escape:1")
    with pytest.raises(ArtifactError):
        citation(tmp_path, "t/test_x.py:999")


def test_ac_123_licoes_apenas_aceitas_atuais_e_no_escopo(tmp_path):
    project(tmp_path)
    v = add_lesson(tmp_path, "agenda", "mock não prova persistência", "consultar o registro salvo", ["t/test_x.py:1"])
    assert v.id == "LESSON-001" and not context(tmp_path, "agenda")["accepted"]
    assert not build(core.load(tmp_path), "agenda", "plan")["lessons"]["accepted"]
    accept_lesson(tmp_path, v.id, "Luciano")
    assert len(context(tmp_path, "agenda")["accepted"]) == 1
    assert not context(tmp_path, "outra")["accepted"]
    packet = build(core.load(tmp_path), "agenda", "plan")
    assert packet["lessons"]["accepted"][0]["accepted_by"] == "Luciano"
    (tmp_path / "t/test_x.py").write_text("# mudou\n", encoding="utf-8")
    ctx = context(tmp_path, "agenda")
    assert not ctx["accepted"] and len(ctx["stale"]) == 1
    with pytest.raises(ArtifactError):
        accept_lesson(tmp_path, v.id, "outro")
    with pytest.raises(ArtifactError):
        add_lesson(tmp_path, "*", "causa", "prevenção", [])


def test_ac_123_cli_licoes_e_dados_invalidos(tmp_path):
    project(tmp_path)
    result = invoke(tmp_path, "lesson", "add", "--cause", "causa", "--prevention", "regressão",
                    "--evidence", "t/test_x.py:1")
    assert result.exit_code == 0, result.output
    assert invoke(tmp_path, "lesson", "accept", "LESSON-001", "--reviewer", "Luciano").exit_code == 0
    assert json.loads(invoke(tmp_path, "lesson", "list").stdout)["lessons"][0]["status"] == "accepted"
    assert invoke(tmp_path, "lesson", "accept", "LESSON-999").exit_code == 2
    assert invoke(tmp_path, "cite", "t/test_x.py:1").exit_code == 0
    (tmp_path / "specs/lessons.yaml").write_text("version: 1\nlessons: [\n", encoding="utf-8")
    assert invoke(tmp_path, "guide", "agenda").exit_code == 2


def changed_proposal(root, name="corrigir-agenda"):
    changes.propose(root, name, "agenda", "incluir garantia de persistência")
    path = f"specs/changes/{name}/spec.yaml"
    spec = load_yaml(root / path)
    spec["requirements"][0]["acceptance"][0]["then"] = "cria reserva persistida"
    save(root, path, spec)
    return path


def test_ac_124_ciclo_proposta_delta_apply_archive_com_check_atual(tmp_path):
    project(tmp_path)
    before = digest(tmp_path / SPEC_PATH)
    changed_proposal(tmp_path)
    assert digest(tmp_path / SPEC_PATH) == before
    change, _, delta = changes.inspect(tmp_path, "corrigir-agenda")
    assert delta["modified"] == ["AC-001", "REQ-001"]
    assert change.status == "draft"
    assert changes.apply(tmp_path, "corrigir-agenda")["verification"] == "NÃO_EXECUTADA"
    assert digest(tmp_path / SPEC_PATH) != before
    result = changes.archive(tmp_path, "corrigir-agenda")
    assert result["status"] == "archived"
    stored = json.loads((tmp_path / "specs/changes/corrigir-agenda/verification.json").read_text(encoding="utf-8"))
    assert stored["ok"] and len(stored["criteria"]) == 3
    with pytest.raises(ArtifactError):
        changes.apply(tmp_path, "corrigir-agenda")


def test_ac_124_conflito_invalidade_e_baseline_preservados(tmp_path):
    project(tmp_path)
    proposal = changed_proposal(tmp_path)
    original = (tmp_path / SPEC_PATH).read_bytes()
    spec = load_yaml(tmp_path / proposal)
    spec["requirements"][0]["acceptance"][0]["then"] = "PREENCHER: resultado"
    save(tmp_path, proposal, spec)
    with pytest.raises(ArtifactError, match="inválida"):
        changes.apply(tmp_path, "corrigir-agenda")
    assert (tmp_path / SPEC_PATH).read_bytes() == original
    assert load_yaml(tmp_path / "specs/changes/corrigir-agenda/change.yaml")["status"] == "draft"
    (tmp_path / SPEC_PATH).write_text(original.decode() + "\n", encoding="utf-8")
    with pytest.raises(ArtifactError, match="reconcilie"):
        changes.apply(tmp_path, "corrigir-agenda")
    with pytest.raises(ArtifactError):
        changes.propose(tmp_path, "corrigir-agenda", "agenda", "duplicado")
    with pytest.raises(ArtifactError):
        changes.propose(tmp_path, "../escape", "agenda", "teste")


def test_ac_124_archive_nao_usa_relatorio_antigo(tmp_path):
    project(tmp_path)
    changed_proposal(tmp_path)
    changes.apply(tmp_path, "corrigir-agenda")
    (tmp_path / "t/test_x.py").write_text("def test_ac_001(): assert False\n", encoding="utf-8")
    with pytest.raises(ArtifactError, match="check atual reprovou"):
        changes.archive(tmp_path, "corrigir-agenda")
    assert load_yaml(tmp_path / "specs/changes/corrigir-agenda/change.yaml")["status"] == "applied"


OPEN = '''## ADDED Requirements
### Requirement: Persistir pedido
O sistema deve salvar o pedido.
#### Scenario: Sucesso
- **WHEN** envia pedido
- **THEN** salva o pedido
- **AND** retorna o identificador
'''
SPECKIT = '''### User Story 1 - Criar pedido
**Acceptance Scenarios**:
1. **Given** carrinho válido, **When** confirma, **Then** salva pedido
2. **Given** carrinho vazio, **When** confirma, **Then** rejeita pedido
'''


@pytest.mark.parametrize("kind,text,count", [("openspec", OPEN, 1), ("speckit", SPECKIT, 2)])
def test_ac_125_importa_rascunho_com_fonte_hash_e_ids_sem_alterar_vigentes(tmp_path, kind, text, count):
    project(tmp_path)
    source = tmp_path / "external.md"
    source.write_text(text, encoding="utf-8")
    before = (tmp_path / SPEC_PATH).read_bytes()
    report = import_spec(tmp_path, "external.md", kind, "pedidos")
    draft = load_yaml(tmp_path / report["draft"])
    acs = draft["requirements"][0]["acceptance"]
    assert len(acs) == count and acs[0]["id"] == "AC-004"
    assert report["sha256"] == digest(source) and report["status"] == "draft"
    assert "PREENCHER" in draft["summary"] and report["warnings"]
    assert (tmp_path / "specs/imports/pedidos/source.md").read_text(encoding="utf-8") == text
    assert (tmp_path / SPEC_PATH).read_bytes() == before and not core.load(tmp_path).errors
    if kind == "openspec":
        assert "PREENCHER" in acs[0]["given"] and acs[0]["then"] == "salva o pedido; retorna o identificador"
    else:
        assert acs[0]["given"] == "carrinho válido" and acs[0]["then"] == "salva pedido"
    with pytest.raises(ArtifactError):
        import_spec(tmp_path, "external.md", kind, "pedidos")


def test_ac_125_import_nao_adivinha_formato_ou_cenarios(tmp_path):
    project(tmp_path)
    for text in ("texto desconhecido", "```markdown\n" + OPEN + "\n```"):
        (tmp_path / "source.md").write_text(text, encoding="utf-8")
        assert invoke(tmp_path, "import-spec", "source.md", "--format", "openspec", "--feature", "nova").exit_code == 2
    with pytest.raises(ArtifactError):
        parse(OPEN, "unknown")
    assert not (tmp_path / "specs/imports/nova").exists()


@pytest.mark.parametrize("field", ["implementer", "reviewer"])
def test_ac_122_revisao_com_identidade_ausente_reprova(tmp_path, field):
    project(tmp_path)
    path, value = review(tmp_path)
    value[field] = " "
    save(tmp_path, path, value)
    assert not adequacy(tmp_path, "agenda")["ok"]


@pytest.mark.parametrize("target", [SPEC_PATH, "specs/changes/corrigir-agenda/spec.yaml"])
def test_ac_124_archive_recusa_qualquer_lado_alterado_apos_apply(tmp_path, target):
    project(tmp_path)
    changed_proposal(tmp_path)
    changes.apply(tmp_path, "corrigir-agenda")
    path = tmp_path / target
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ArtifactError, match="inalterada"):
        changes.archive(tmp_path, "corrigir-agenda")
    assert not (tmp_path / "specs/changes/corrigir-agenda/verification.json").exists()
