"""Revisão escalonada: piso de risco, achados de LLM, correções como casos, adequação humana."""
import copy
import hashlib
import json

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from sdd import core
from sdd.artifacts import ArtifactError
from sdd.cli import app
from sdd.governance import file_tier, findings, fixes, higher, rank, render_risk, risk
from sdd.learning import adequacy, save
from sdd.models import ReviewConfig
from sdd.workflow import build

from test_analise import SPEC, project
from test_complementos import review
from test_diff import commit, git, write

runner = CliRunner()


def invoke(root, *args):
    return runner.invoke(app, [*args, "-C", str(root)])


def design(*severities):
    return {
        "numbers": [{"metric": "m", "max": 1, "unit": "u", "source": "s"}],
        "data_flow": {"ingress": [{"via": "v", "frequency": "f"}], "egress": [{"to": "t"}]},
        "alternatives": [{"name": "a", "chosen": True, "why": "w"}, {"name": "b", "why_not": "n"}],
        "risks": [{"area": "security", "severity": s, "description": "d", "accepted": "ok"} for s in severities],
        "dependencies": [],
    }


REVIEW = {"tiers": {"low": ["docs/**", "*.md"], "high": [".github/**", "src/auth/**"]},
          "default_tier": "medium"}


def setup(root, review_cfg=None, severities=None, paths=("src/agenda/**",)):
    spec = copy.deepcopy(SPEC)
    spec["paths"] = list(paths)
    if severities:
        spec["design"] = design(*severities)
    project(root, spec, {"review": REVIEW if review_cfg is None else review_cfg})
    return core.load(root)


def tier_of(rep, path):
    return next(f["tier"] for f in rep["files"] if f["path"] == path)


# --- REQ-039: piso de risco ------------------------------------------------------------

def test_ac_126_tier_por_glob_default_specs_e_risco_da_spec_dona(tmp_path):
    proj = setup(tmp_path, severities=["low", "high"])
    assert not proj.errors, proj.errors
    rep = risk(proj, ["docs/a.md", "README.md", "src/outro.py", ".github/ci.yml"])
    assert tier_of(rep, "docs/a.md") == "low" and tier_of(rep, "README.md") == "low"
    assert tier_of(rep, "src/outro.py") == "medium" and tier_of(rep, ".github/ci.yml") == "high"
    assert rep["tier"] == rep["floor"] == "high" and rep["required_approvals"] == 2
    assert rep["status"] == "INFORMATIVO" and rep["ok"] and rep["approvals"] is None
    tier, reasons = file_tier(proj, proj.config.review, "src/agenda/x.py")
    assert tier == "high" and any("agenda: risco high (security)" in r for r in reasons)
    tier, reasons = file_tier(proj, proj.config.review, "specs/features/FEATURE-001/spec.yaml")
    assert tier == "high" and reasons == ["review.default_tier (medium)", "agenda: risco high (security)"]
    low = risk(proj, ["docs/a.md"])
    assert low["tier"] == "low" and low["required_approvals"] == 0 and low["files"][0]["reasons"] == ["review.tiers.low"]


def test_ac_126_specs_tem_minimo_medium_e_maior_glob_vence(tmp_path):
    proj = setup(tmp_path, {"tiers": {"low": ["specs/**", "src/**"], "high": ["src/auth/**"]},
                            "default_tier": "low"})
    cfg = proj.config.review
    tier, reasons = file_tier(proj, cfg, "specs/decisions.yaml")
    assert tier == "medium" and reasons == ["review.tiers.low", "contrato do projeto (specs/): mínimo medium"]
    tier, reasons = file_tier(proj, cfg, "specs/sdd.yaml")
    assert tier == "high" and reasons == ["review.tiers.low", "specs/sdd.yaml define gates e o próprio piso: high"]
    assert file_tier(proj, setup(tmp_path).config.review, "specs/x.yaml")[1] == ["review.default_tier (medium)"]
    assert file_tier(proj, cfg, "src/auth/login.py")[0] == "high"
    assert file_tier(proj, cfg, "outro.txt") == ("low", ["review.default_tier (low)"])
    none = risk(proj, [])
    assert none["tier"] == "low" and none["notes"] == ["nenhum arquivo alterado"]
    assert risk(proj, [".sdd/risk.json", ".sdd/review/escalations.json"])["files"] == []
    assert risk(proj, ["src/a.py", "src/a.py"])["files"] == [
        {"path": "src/a.py", "tier": "low", "reasons": ["review.tiers.low"]}]


def test_ac_126_risco_medio_eleva_low_mas_nao_rebaixa(tmp_path):
    proj = setup(tmp_path, {"tiers": {"low": ["src/**"], "high": ["src/agenda/secreto.py"]}},
                 severities=["medium"])
    cfg = proj.config.review
    tier, reasons = file_tier(proj, cfg, "src/agenda/x.py")
    assert tier == "medium" and reasons[-1] == "agenda: risco medium (security)"
    assert file_tier(proj, cfg, "src/agenda/secreto.py") == ("high", ["review.tiers.high"])
    assert file_tier(proj, cfg, "src/fora.py") == ("low", ["review.tiers.low"])


def test_ac_126_approvals_invalido_e_erro_de_config(tmp_path):
    for bad in ({"low": 0, "medium": 1}, {"low": 1, "medium": 0, "high": 2}, {"low": -1, "medium": 0, "high": 0}):
        with pytest.raises(ValidationError, match="approvals"):
            ReviewConfig(approvals=bad)
    assert ReviewConfig(approvals={"low": 0, "medium": 0, "high": 0}).approvals["high"] == 0
    proj = setup(tmp_path, {"approvals": {"low": 0, "medium": 2, "high": 1}})
    assert any("approvals" in e for e in proj.errors)
    assert rank("low") < rank("medium") < rank("high")
    assert higher("medium", "high") == "high" and higher("high", "low") == "high" and higher("low", "low") == "low"


def escalate(root, *items):
    write(root, ".sdd/review/escalations.json", json.dumps({"version": 1, "escalations": list(items)}))


def test_ac_127_escalacao_so_eleva_e_autor_fora_da_lista(tmp_path):
    proj = setup(tmp_path, {**REVIEW, "trusted_authors": ["luciano"]})
    escalate(tmp_path, {"tier": "low", "reason": "parece trivial", "source": "classificador"},
             {"tier": "high", "reason": "mexe em autorização", "source": "classificador"},
             {"tier": "medium", "reason": "outro", "source": "revisor"})
    rep = risk(proj, ["docs/a.md"], author="luciano")
    assert rep["floor"] == "low" and rep["tier"] == "high" and rep["required_approvals"] == 2
    assert [e["tier"] for e in rep["escalations"]["applied"]] == ["high"]
    assert [e["tier"] for e in rep["escalations"]["ignored"]] == ["low", "medium"]
    assert all("nunca reduz" in e["why"] for e in rep["escalations"]["ignored"])
    assert rep["trusted"] is True
    (tmp_path / ".sdd/review/escalations.json").unlink()
    trusted = risk(proj, ["docs/a.md"], author="luciano")
    assert trusted["required_approvals"] == 0 and trusted["notes"] == []
    for author in ("bot", None):
        other = risk(proj, ["docs/a.md"], author=author)
        assert other["required_approvals"] == 1 and other["trusted"] is False
        assert "trusted_authors" in other["notes"][0]
    assert risk(proj, [".github/x.yml"], author="bot")["required_approvals"] == 2
    assert risk(setup(tmp_path), ["docs/a.md"], author="qualquer")["trusted"] is None


def test_ac_127_aprovacoes_e_codigos_de_saida(repo_review):
    root = repo_review
    write(root, ".github/ci.yml", "x: 1\n")
    commit(root)
    result = invoke(root, "risk", "--base", "main")
    assert result.exit_code == 0 and "tier high" in result.stdout and "2 aprovação" in result.stdout
    assert invoke(root, "risk", "--base", "main", "--approvals", "1").exit_code == 1
    ok = invoke(root, "risk", "--base", "main", "--approvals", "2", "--json")
    assert ok.exit_code == 0 and json.loads(ok.stdout)["status"] == "APROVADO"
    assert json.loads((root / ".sdd/risk.json").read_text(encoding="utf-8"))["tier"] == "high"
    assert "| .github/ci.yml | high |" in (root / ".sdd/risk.md").read_text(encoding="utf-8")
    write(root, ".sdd/review/escalations.json", '{"version": 1, "escalations": [{"tier": "low"}]}')
    assert invoke(root, "risk", "--base", "main").exit_code == 2
    write(root, ".sdd/review/escalations.json", '{"version": 1, "escalations": [{"tier": "high", '
          '"reason": "r", "source": "s"}]}')
    lines = invoke(root, "risk", "--base", "main").stdout.splitlines()
    assert lines[0] == "high    .github/ci.yml  (review.tiers.high)"  # coluna de 7 + espaço
    escalated = invoke(root, "risk", "--base", "main")
    assert escalated.exit_code == 0 and "escalado para high por s" not in escalated.stdout
    assert invoke(root, "risk", "--base", "inexistente").exit_code == 2
    (root / ".sdd/review/escalations.json").unlink()
    write(root, "docs/a.md", "x\n")
    git(root, "rm", "-q", ".github/ci.yml")
    commit(root)
    zero = invoke(root, "risk", "--base", "main", "--approvals", "0")
    assert zero.exit_code == 0 and "0 de 0 aprovação" in zero.stdout
    assert invoke(root, "risk", "--base", "main", "--approvals", "-1").exit_code == 2


def test_ac_127_json_valido_com_avisos_do_projeto(repo_review):
    root = repo_review
    spec = copy.deepcopy(SPEC)
    spec["paths"] = ["src/agenda/**"]
    spec["requirements"][1]["acceptance"][0]["then"] = "lista horários rapidamente"  # critério vago: aviso
    project(root, spec)
    write(root, "docs/a.md", "x\n")
    commit(root)
    for args in (["risk", "--base", "main", "--json"], ["findings", "--json"], ["fixes"]):
        result = invoke(root, *args)
        assert isinstance(json.loads(result.stdout), dict), args
        assert "critério vago" in result.stderr and "critério vago" not in result.stdout


@pytest.fixture
def repo_review(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    setup(tmp_path)
    commit(tmp_path, "base")
    git(tmp_path, "checkout", "-qb", "trabalho")
    return tmp_path


def test_ac_127_cli_mostra_escalacao_aplicada(repo_review):
    root = repo_review
    write(root, "docs/a.md", "x\n")
    commit(root)
    escalate(root, {"tier": "high", "reason": "toca auth", "source": "classificador"})
    result = invoke(root, "risk", "--base", "main")
    assert result.exit_code == 0 and "escalado para high por classificador: toca auth" in result.stdout
    assert "tier high (piso low)" in result.stdout
    md = (root / ".sdd/risk.md").read_text(encoding="utf-8")
    assert "## Escalações aplicadas" in md and "aprovação de agente não conta" in md
    (root / ".sdd/review/escalations.json").unlink()
    proj = setup(root, {**REVIEW, "trusted_authors": ["luciano"]})
    md = render_risk(risk(proj, ["docs/a.md"], author="bot"))
    assert md.endswith("## Notas\n\n- autor fora de trusted_authors (ou não informado): mínimo de 1 "
                       "aprovação humana\n")


# --- REQ-040: achados de revisor LLM -------------------------------------------------------

def sha(root, rel):
    return hashlib.sha256((root / rel).read_bytes()).hexdigest()


def finding(fid="F1", **kw):
    return {"id": fid, "severity": "important", "path": "t/test_x.py", "line": 1,
            "message": f"mensagem {fid}", "votes": 3, "voters": 3, "round": 1, **kw}


def record(root, items, round_=1, reviewed=None):
    doc = {"version": 1, "reviewer": "loopway/claude", "round": round_,
           "reviewed": reviewed or {"t/test_x.py": sha(root, "t/test_x.py")}, "findings": items}
    write(root, ".sdd/review/findings.json", json.dumps(doc))


def test_ac_128_ausente_politica_e_natureza_probabilistica(tmp_path):
    proj = setup(tmp_path, {"allow_llm_findings": False})
    rep = findings(proj)
    assert rep["ok"] and rep["state"] == "AUSENTE" and rep["evidence"] == "probabilística"
    assert rep["counts_as_human_approval"] is False
    result = invoke(tmp_path, "findings")
    assert result.exit_code == 0 and "nenhum achado" in result.stdout
    record(tmp_path, [])
    rep = findings(core.load(tmp_path))
    assert not rep["ok"] and any("allow_llm_findings" in p for p in rep["problems"])
    setup(tmp_path, {"allow_llm_findings": True})
    rep = findings(core.load(tmp_path))
    assert rep["ok"] and rep["state"] == "APROVADO" and rep["reviewer"] == "loopway/claude"
    assert rep["counts_as_human_approval"] is False and "não conta como aprovação humana" in rep["scope"]
    out = invoke(tmp_path, "findings")
    assert out.exit_code == 0 and "evidência probabilística" in out.stdout
    md = (tmp_path / ".sdd/findings.md").read_text(encoding="utf-8")
    assert "evidência probabilística" in md and "Rodada 1: 0 achado(s)" in md


def test_ac_129_bloqueio_consenso_e_destinos(tmp_path):
    setup(tmp_path, {"allow_llm_findings": True})
    record(tmp_path, [
        finding("F1"),
        finding("F2", severity="nit"),
        finding("F3", severity="pre_existing"),
        finding("F4", votes=1, voters=2),
        finding("F5", status="fixed"),
        finding("F6", status="dismissed", disposition="wrong", reason="o teste já cobre"),
        finding("F7", status="dismissed", disposition="intentional", reason="comportamento desejado"),
    ])
    rep = findings(core.load(tmp_path))
    assert not rep["ok"] and [b["id"] for b in rep["blocking"]] == ["F1"]
    assert rep["problems"] == ["F1: achado important aberto em t/test_x.py:1"]
    s = rep["summary"]
    assert s["total"] == 7 and s["by_status"] == {"open": 4, "fixed": 1, "dismissed": 2}
    assert s["by_severity"] == {"important": 5, "nit": 1, "pre_existing": 1}
    assert s["dismissed_as"] == {"wrong": 1, "intentional": 1, "irrelevant": 0}
    assert s["without_consensus"] == 1 and s["round"] == 1
    assert invoke(tmp_path, "findings").exit_code == 1
    as_json = invoke(tmp_path, "findings", "--json").stdout
    assert json.loads(as_json)["state"] == "REPROVADO"
    assert '"evidence": "probabilística"' in as_json and as_json.startswith('{\n  "report_version"')
    record(tmp_path, [finding("F1", votes=2, voters=4)])
    assert findings(core.load(tmp_path))["ok"]
    record(tmp_path, [finding("F1", votes=3, voters=4)])
    assert not findings(core.load(tmp_path))["ok"]


def test_ac_129_descartado_exige_destino_e_dados_invalidos(tmp_path):
    setup(tmp_path, {"allow_llm_findings": True})
    for bad in (finding(status="dismissed"), finding(status="dismissed", disposition="wrong"),
                finding(disposition="wrong", reason="r"), finding(votes=4, voters=3)):
        record(tmp_path, [bad])
        with pytest.raises(ArtifactError):
            findings(core.load(tmp_path))
    write(tmp_path, ".sdd/review/findings.json", "{")
    assert invoke(tmp_path, "findings").exit_code == 2


def test_ac_129_revisao_desatualizada_repeticao_e_teto_de_rodadas(tmp_path):
    setup(tmp_path, {"allow_llm_findings": True, "max_rounds": 2})
    record(tmp_path, [finding("F1", status="fixed")])
    assert findings(core.load(tmp_path))["ok"]
    (tmp_path / "t/test_x.py").write_text("def test_ac_001(): pass\n", encoding="utf-8")
    rep = findings(core.load(tmp_path))
    assert not rep["ok"] and rep["stale"] == ["t/test_x.py"] and "desatualizada" in rep["problems"][0]
    record(tmp_path, [], reviewed={"t/sumiu.py": "0" * 64})
    assert findings(core.load(tmp_path))["stale"] == ["t/sumiu.py"]
    record(tmp_path, [finding("F1", status="fixed"), finding("F1", status="fixed", message="outra")])
    assert findings(core.load(tmp_path))["problems"] == ["ID de achado repetido: F1"]
    record(tmp_path, [finding("F1", status="fixed", message="Teste  FRACO"),
                      finding("F2", status="fixed", message="teste fraco", round=2)], round_=2)
    assert findings(core.load(tmp_path))["problems"] == ["F2: repete o achado F1 (mesmo arquivo e mensagem)"]
    record(tmp_path, [finding("F1", status="fixed", message="m", path="t/test_x.py"),
                      finding("F2", status="fixed", message="m", line=1, path="t/outro.py")])
    assert findings(core.load(tmp_path))["ok"]
    record(tmp_path, [finding("F1", status="fixed", round=2)], round_=1)
    assert findings(core.load(tmp_path))["problems"] == ["F1: rodada 2 posterior à rodada atual 1"]
    record(tmp_path, [], round_=2)
    assert findings(core.load(tmp_path))["ok"]
    record(tmp_path, [], round_=3)
    rep = findings(core.load(tmp_path))
    assert rep["problems"] == ["rodada 3 excede review.max_rounds=2: reveja a abordagem em vez de mais uma rodada"]


# --- REQ-041: correções como casos de avaliação -------------------------------------------

def test_ac_130_exporta_so_commits_com_sdd_fix(repo_review):
    root = repo_review
    base = git(root, "rev-parse", "HEAD").strip()
    write(root, "src/agenda/x.py", "x = 1\n")
    write(root, "t/test_x.py", "def test_ac_001(): pass\ndef test_ac_002(): pass\ndef test_ac_003(): pass\n# r\n")
    commit(root, "corrige reserva\n\nSDD-Fix: AC-001, AC-002")
    write(root, "docs/a.md", "x\n")
    commit(root, "docs")
    write(root, "src/agenda/z.py", "z = 1\n")
    commit(root, "separador \x1f na mensagem\n\nSDD-Fix: AC-003")
    rep = fixes(core.load(root), base)
    assert [r["criteria"] for r in rep["fixes"]] == [["AC-003"], ["AC-001", "AC-002"]]
    rep["fixes"] = rep["fixes"][1:]
    assert rep["ok"] and rep["range"] == f"{base}..HEAD" and len(rep["fixes"]) == 1
    row = rep["fixes"][0]
    assert row["criteria"] == ["AC-001", "AC-002"] and row["features"] == ["agenda"]
    assert row["files"] == ["src/agenda/x.py", "t/test_x.py"] and row["tests"] == ["t/test_x.py"]
    assert len(row["commit"]) == 40 and "não comprova" in rep["scope"]
    assert fixes(core.load(root))["range"] == "HEAD"
    write(root, "src/agenda/y.py", "y = 1\n")
    commit(root, "corrige\n\nSDD-Fix: AC-404")
    rep = fixes(core.load(root), base)
    assert not rep["ok"] and rep["problems"][0].endswith(": AC-404")
    result = invoke(root, "fixes", "--base", base)
    assert result.exit_code == 1 and json.loads(result.stdout)["fixes"][0]["criteria"] == ["AC-404"]
    assert "não comprova" in result.stdout and result.stdout.startswith('{\n  "report_version"')
    with pytest.raises(ArtifactError):
        fixes(core.load(root), "inexistente")


# --- REQ-035 (FEATURE-011): adequação humana -------------------------------------------------

def test_ac_131_adequacao_exige_humano_por_risco_ou_config(tmp_path):
    setup(tmp_path)
    path, value = review(tmp_path)
    rep = adequacy(tmp_path, "agenda")
    assert rep["ok"] and rep["human_required"] == [] and rep["evidence"] == "probabilística"
    setup(tmp_path, {"human_adequacy": ["agen*"]})
    rep = adequacy(tmp_path, "agenda")
    assert not rep["ok"] and rep["human_required"] == ["feature listada em review.human_adequacy"]
    assert "revisor humano exigido" in rep["problems"][0]
    setup(tmp_path, severities=["high"])
    (tmp_path / "specs/reviews/agenda.yaml").unlink()
    path, value = review(tmp_path)
    rep = adequacy(tmp_path, "agenda")
    assert rep["human_required"] == ["spec com risco high"] and not rep["ok"]
    value["reviewer_kind"] = "human"
    save(tmp_path, path, value)
    rep = adequacy(tmp_path, "agenda")
    assert rep["ok"] and rep["evidence"] == "humana declarada"
    setup(tmp_path, severities=["medium"])
    (tmp_path / "specs/reviews/agenda.yaml").unlink()
    review(tmp_path)
    assert adequacy(tmp_path, "agenda")["human_required"] == []


# --- REQ-024 (FEATURE-009): convergência ---------------------------------------------------

def test_ac_132_converge_pede_convergencia_com_teto_configurado(tmp_path):
    setup(tmp_path, {"max_rounds": 4})
    packet = build(core.load(tmp_path), "agenda", "converge")
    text = "\n".join(packet["instructions"])
    assert "não repita lacunas" in text and "pre_existing não bloqueia" in text
    assert "classe do problema" in text and "só o diff novo" in text
    assert "review.max_rounds (atual: 4)" in text and "{max_rounds}" not in text
    assert {"sdd risk --base <ref-alvo>", "sdd findings"} <= set(packet["conditional_verification"])
    plan = build(core.load(tmp_path), "agenda", "plan")
    assert not any("max_rounds" in t for t in plan["instructions"])
    setup(tmp_path, {})
    assert "(atual: 3)" in "\n".join(build(core.load(tmp_path), "agenda", "converge")["instructions"])
