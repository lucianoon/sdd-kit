"""Actual retrieval, cached state, emitted traces and evaluation snapshots."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import Limits, Rag, audit  # noqa: E402
from evaluate import INPUTS, METRICS, ROOT, benchmark, compare, percentile95, run, snapshot  # noqa: E402


def documents():
    return json.loads((ROOT / "documents.json").read_text(encoding="utf-8"))


@pytest.fixture
def project(tmp_path):
    for name in INPUTS:
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    return tmp_path


def test_ac_001_recupera_cita_e_isola_tenants():
    engine = Rag(documents())
    a = engine.answer("refund", "a", ["refund-a", "refund-b"])
    b = engine.answer("refund", "b", ["refund-a", "refund-b"])
    assert a["answer"] == "O prazo de reembolso é 14 dias."
    assert a["citations"] == [{"id": "refund-a", "version": 2}]
    assert b["answer"] == "O prazo de reembolso é 30 dias."
    assert b["citations"] == [{"id": "refund-b", "version": 1}]
    assert engine.answer("refund", "a", ["refund-b"])["answer"] is None


def test_ac_002_fontes_ausentes_revogadas_e_cache_atual():
    engine = Rag(documents())
    assert engine.answer("unknown", "a", ["refund-a"])["answer"] is None
    assert engine.answer("legacy", "a", ["retired-a"])["citations"] == []
    engine.answer("refund", "a", ["refund-a"])
    cached = engine.answer("refund", "a", ["refund-a"])
    assert [s["operation"] for s in cached["trace"]["spans"]] == ["cache"]
    assert engine.answer("refund", "a", [])["answer"] is None
    engine.documents[0].update(version=3, text="O prazo é 21 dias.")
    refreshed = engine.answer("refund", "a", ["refund-a"])
    assert refreshed["answer"] == "O prazo é 21 dias."
    assert refreshed["citations"] == [{"id": "refund-a", "version": 3}]
    engine.documents[0]["active"] = False
    assert engine.answer("refund", "a", ["refund-a"])["answer"] is None
    engine.documents.pop(0)
    assert engine.answer("refund", "a", ["refund-a"])["answer"] is None


def test_ac_003_fallback_preserva_contrato_e_degradacao():
    normal = Rag(documents()).answer("refund", "a", ["refund-a"])
    fallback = Rag(documents()).answer("refund", "a", ["refund-a"], primary_down=True)
    assert fallback["answer"] == normal["answer"] and fallback["citations"] == normal["citations"]
    assert [s["operation"] for s in fallback["trace"]["spans"]] == ["retrieve", "primary", "fallback"]
    assert fallback["trace"]["spans"][1]["status"] == "error"
    down = Rag(documents()).answer("refund", "a", ["refund-a"], primary_down=True, fallback_down=True)
    assert down["answer"] is None and down["citations"] == []
    assert not audit(fallback["trace"], Limits())


@pytest.mark.parametrize("limits,problem", [(Limits(max_calls=1), "work_budget"),
                                            (Limits(max_steps=1), "work_budget"),
                                            (Limits(deadline_ms=0), "deadline")])
def test_ac_004_interrompe_orcamento(limits, problem):
    with pytest.raises(RuntimeError, match=problem):
        Rag(documents()).answer("refund", "a", ["refund-a"], limits=limits)


def test_ac_004_audita_efeito_custo_escopo_e_ordem():
    good = Rag(documents()).answer("refund", "a", ["refund-a"])["trace"]
    assert not audit(good, Limits())
    for field, value, expected in [("operation", "delete", "forbidden_operation"),
                                    ("tenant", "b", "tenant_scope"),
                                    ("cost_usd", 0.5, "cost_budget"),
                                    ("cost_usd", float("nan"), "cost_budget")]:
        trace = copy.deepcopy(good)
        trace["spans"][0][field] = value
        assert expected in audit(trace, Limits())
    trace = copy.deepcopy(good)
    trace["spans"].reverse()
    assert "generation_without_retrieval" in audit(trace, Limits())
    assert "answer" not in good and "question" not in good
    assert len(good["question_sha256"]) == 64


def test_ac_005_manifesto_e_resultados_brutos(project):
    manifest = run(project)
    assert manifest["runs"] == 3 and len(manifest["cases"]) == 7
    assert set(manifest["inputs"]) == set(INPUTS)
    assert manifest["scope"] == "offline_fixture_not_llm_quality"
    _, payload = snapshot(project, ".sdd/evals")
    assert len(payload["results.jsonl"]) == 21
    assert all(all(v == 1 for v in r["scores"].values()) for r in payload["results.jsonl"])
    for identity in METRICS:
        rows = [json.loads(line) for line in (project / f".sdd/evals/{identity}.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 21 and all(r["score"] == 1 for r in rows)
    raw = (project / ".sdd/evals/traces.jsonl").read_text(encoding="utf-8")
    assert "14 dias" not in raw and '"question":' not in raw


def test_ac_006_comparacao_detecta_regressao_e_recusa_incomparavel(project, monkeypatch):
    run(project, ".sdd/baseline")
    run(project, ".sdd/candidate")
    assert compare(project, ".sdd/baseline", ".sdd/candidate")["ok"]
    import evaluate
    class Broken(Rag):
        def answer(self, *args, **kwargs):
            result = super().answer(*args, **kwargs)
            result["answer"] = "inventado"
            return result
    monkeypatch.setattr(evaluate, "Rag", Broken)
    run(project, ".sdd/candidate")
    result = compare(project, ".sdd/baseline", ".sdd/candidate")
    assert not result["ok"]
    assert any(r["case"] == "answer-a" and r["category"] == "grounding" and r["metric"] == "outcome" for r in result["regressions"])
    (project / "cases.jsonl").write_text((project / "cases.jsonl").read_text(encoding="utf-8") + "\n", encoding="utf-8")
    run(project, ".sdd/candidate")
    with pytest.raises(ValueError, match="incomparable"):
        compare(project, ".sdd/baseline", ".sdd/candidate")


def test_ac_006_artefato_adulterado_nao_e_baseline_valida(project):
    run(project)
    p = project / ".sdd/evals/results.jsonl"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        snapshot(project, ".sdd/evals")
    with pytest.raises(ValueError):
        run(project, "../fora")


def test_ac_007_p95_nao_e_media_nem_ttft(project):
    assert percentile95([1] * 18 + [20, 100]) == 20
    run(project)
    report = benchmark(project, ".sdd/evals", 1000)
    assert report["ok"] and report["ttft_ms"] is None and report["p95_ms"] >= 0
    assert not benchmark(project, ".sdd/evals", 0)["ok"]
    with pytest.raises(ValueError):
        percentile95([float("nan")])


def test_ac_004_cancelamento_na_admissao_nao_inicia_chamadas():
    trace = Rag(documents()).answer("refund", "a", ["refund-a"], cancelled=True)["trace"]
    assert [s["operation"] for s in trace["spans"]] == ["cancel"]
    assert not any(s["call"] for s in trace["spans"])
    assert not audit(trace, Limits())
    trace["spans"].append({"operation": "retrieve", "call": True, "status": "ok", "tenant": "a", "cost_usd": 0})
    assert "action_after_cancel" in audit(trace, Limits())


@pytest.mark.parametrize("damage", ["duplicate", "missing", "boolean-score"])
def test_ac_006_cobertura_e_tipo_invalidos_mesmo_com_hash_recalculado(project, damage):
    import hashlib
    run(project)
    p = project / ".sdd/evals/results.jsonl"
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
    if damage == "duplicate":
        rows.append(rows[0])
    elif damage == "missing":
        rows.pop()
    else:
        rows[0]["scores"]["outcome"] = True
    content = "".join(json.dumps(r) + "\n" for r in rows).encode("utf-8")
    p.write_bytes(content)
    meta = project / ".sdd/evals/manifest.json"
    manifest = json.loads(meta.read_text(encoding="utf-8"))
    manifest["artifacts"]["results.jsonl"] = hashlib.sha256(content).hexdigest()
    meta.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        snapshot(project, ".sdd/evals")


def test_ac_005_nao_rotula_fixture_como_modelo_real(project):
    p = project / "config.json"
    config = json.loads(p.read_text(encoding="utf-8"))
    config["provider"] = "real-api"
    p.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="offline fixture"):
        run(project)


def test_ac_004_contagem_de_chamadas_deriva_das_operacoes_e_tempo_e_finito():
    trace = Rag(documents()).answer("refund", "a", ["refund-a"])["trace"]
    trace["spans"][0]["call"] = False
    assert "call_accounting" in audit(trace, Limits())
    assert "work_budget" in audit(trace, Limits(max_calls=1))
    trace["duration_ms"] = float("nan")
    assert "deadline" in audit(trace, Limits())
    with pytest.raises(ValueError):
        percentile95([True])
