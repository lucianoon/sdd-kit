"""sdd eval: critérios estatísticos para comportamento de LLM."""
import copy
import json
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from sdd import core, evals
from sdd.cli import app
from sdd.models import Eval

runner = CliRunner()
PY = sys.executable

# Harness falso: lê plan.json e grava os resultados brutos que o "agente" teria produzido.
HARNESS = '''\
import json, pathlib
plan = json.loads(pathlib.Path("plan.json").read_text(encoding="utf-8"))
out = pathlib.Path(".sdd/evals"); out.mkdir(parents=True, exist_ok=True)
for eval_id, lines in plan.items():
    (out / f"{eval_id}.jsonl").write_text(encoding="utf-8", data="".join(json.dumps(l) + "\\n" for l in lines))
'''

EVAL = {"id": "EVAL-001", "metric": "tool_selection_accuracy", "dataset": "evals/tools.jsonl",
        "min_cases": 100, "runs": 3, "threshold": {"min": 0.85}}


def lines_for(rates, n=100, field="pass"):
    out = []
    for run, rate in enumerate(rates, 1):
        for i in range(n):
            val = (i < round(rate * n)) if field == "pass" else rate
            out.append({"case": f"c{i}", "run": run, field: val})
    return out


def project(root: Path, ev: dict | None = None, plan=None, allow_llm=False, cases=100,
            harness=True):
    (root / "specs/features/FEATURE-001").mkdir(parents=True)
    (root / "evals").mkdir()
    (root / "evals/tools.jsonl").write_text(encoding="utf-8", data=
        "".join(json.dumps({"id": f"c{i}", "input": "..."}) + "\n" for i in range(cases)))
    cfg = {"tests": {"command": "true", "junit": "j.xml"},
           "evals": {"allow_llm_judge": allow_llm}}
    if harness:
        cfg["evals"]["command"] = f"{PY} harness.py"
        (root / "harness.py").write_text(encoding="utf-8", data=HARNESS)
        (root / "plan.json").write_text(encoding="utf-8", data=json.dumps(
            {"EVAL-001": plan if plan is not None else lines_for([0.9, 0.91, 0.92])}))
    (root / "specs/sdd.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(cfg))
    spec = {"feature": "agente", "version": 1, "size": "small",
            "requirements": [{"id": "REQ-001", "description": "d",
                              "acceptance": [{"id": "AC-001", "given": "g", "when": "w", "then": "t"}]}],
            "evals": [ev or EVAL]}
    (root / "specs/features/FEATURE-001/spec.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(spec, allow_unicode=True))
    return root


def run_eval(root: Path) -> dict:
    proj = core.load(root)
    assert proj.errors == [], proj.errors
    return evals.run(proj)


def ev_with(**over) -> dict:
    e = copy.deepcopy(EVAL)
    e.update(over)
    return e


def test_ac_034_acima_do_limite_aprova(tmp_path):
    rep = run_eval(project(tmp_path))
    row = rep["evals"][0]
    assert rep["ok"] and row["verdict"] == "OK"
    assert row["value"] == 0.91 and row["runs"] == 3 and row["spread"] == 0.02


def test_ac_034_cli_aprova_e_grava_relatorio(tmp_path):
    r = runner.invoke(app, ["eval", "-C", str(project(tmp_path))])
    assert r.exit_code == 0, r.output
    assert "OK" in r.output and "EVAL-001" in r.output
    assert "APROVADO" in (tmp_path / ".sdd/eval.md").read_text(encoding="utf-8")


def test_ac_035_abaixo_do_limite_reprova(tmp_path):
    rep = run_eval(project(tmp_path, plan=lines_for([0.80, 0.82, 0.81])))
    assert not rep["ok"]
    assert rep["evals"][0]["verdict"] == "FORA_DO_LIMITE"


def test_ac_035_relatorio_lista_o_problema(tmp_path):
    md = evals.render_markdown(run_eval(project(tmp_path, plan=lines_for([0.80, 0.82, 0.81]))))
    assert "REPROVADO" in md and "## Problemas" in md and "- EVAL-001 (agente): FORA_DO_LIMITE" in md


def test_ac_035_limite_maximo(tmp_path):
    ev = ev_with(metric="hallucination_rate", threshold={"max": 0.05})
    rep = run_eval(project(tmp_path, ev, plan=lines_for([0.1, 0.1, 0.1])))
    assert rep["evals"][0]["verdict"] == "FORA_DO_LIMITE"
    assert "> máximo 0.05" in rep["evals"][0]["detail"]


def test_ac_036_execucoes_insuficientes(tmp_path):
    rep = run_eval(project(tmp_path, plan=lines_for([0.9, 0.9])))
    assert rep["evals"][0]["verdict"] == "INCOMPLETO"
    assert "2 execução(ões), exigido 3" in rep["evals"][0]["detail"]


def test_ac_036_casos_insuficientes_por_execucao(tmp_path):
    plan = lines_for([0.9, 0.9, 0.9])
    plan = [l for l in plan if not (l["run"] == 2 and l["case"] == "c99")]
    rep = run_eval(project(tmp_path, plan=plan))
    assert "execução 2 com 99 casos" in rep["evals"][0]["detail"]


def test_ac_036_caso_fora_do_dataset(tmp_path):
    plan = lines_for([0.9, 0.9, 0.9]) + [{"case": "inventado", "run": 1, "pass": True}]
    rep = run_eval(project(tmp_path, plan=plan))
    assert "caso 'inventado' não existe no dataset" in rep["evals"][0]["detail"]


def test_ac_036_caso_duplicado(tmp_path):
    plan = lines_for([0.9, 0.9, 0.9]) + [{"case": "c0", "run": 1, "pass": True}]
    rep = run_eval(project(tmp_path, plan=plan))
    assert "duplicado na execução 1" in rep["evals"][0]["detail"]


def test_ac_037_instavel_entre_execucoes(tmp_path):
    ev = ev_with(max_run_spread=0.05)
    rep = run_eval(project(tmp_path, ev, plan=lines_for([0.99, 0.86, 0.95])))
    row = rep["evals"][0]
    assert row["verdict"] == "INSTAVEL", row
    assert row["spread"] == 0.13


def test_ac_038_juiz_llm_bloqueado_pela_politica(tmp_path):
    project(tmp_path, ev_with(judge="llm"))
    assert any("judge: llm" in e for e in core.load(tmp_path).errors)


def test_ac_038_juiz_llm_permitido_e_sinalizado(tmp_path):
    rep = run_eval(project(tmp_path, ev_with(judge="llm"), allow_llm=True))
    assert rep["ok"]
    md = evals.render_markdown(rep)
    assert "LLM ⚠" in md and "probabilístico" in md


def test_ac_039_resultado_antigo_descartado(tmp_path):
    project(tmp_path)
    (tmp_path / ".sdd/evals").mkdir(parents=True)
    (tmp_path / ".sdd/evals/EVAL-001.jsonl").write_text(encoding="utf-8", data=
        "".join(json.dumps(l) + "\n" for l in lines_for([0.9, 0.9, 0.9])))
    (tmp_path / "plan.json").write_text(encoding="utf-8", data="{}")  # harness desta vez não grava nada
    rep = run_eval(tmp_path)
    assert rep["evals"][0]["verdict"] == "SEM_RESULTADO"


def test_ac_040_limite_inferior_do_intervalo(tmp_path):
    # Média 0.87 passa em min 0.85, mas com 30 casos x 3 a incerteza é grande.
    ev = ev_with(min_cases=30, use_lower_bound=True)
    rep = run_eval(project(tmp_path, ev, plan=lines_for([0.87, 0.87, 0.87], n=30), cases=30))
    row = rep["evals"][0]
    assert row["verdict"] == "FORA_DO_LIMITE", row
    assert row["value"] >= 0.85 and row["ci95"][0] < 0.85
    assert "limite inferior do IC95" in row["detail"]


def test_ac_041_dataset_alterado_sem_spec_reprova_no_diff(tmp_path):
    from test_diff import commit, git, write
    git(tmp_path, "init", "-q", "-b", "main")
    project(tmp_path)
    commit(tmp_path, "base")
    git(tmp_path, "checkout", "-qb", "pr")
    write(tmp_path, "evals/tools.jsonl",
          "".join(json.dumps({"id": f"c{i}"}) + "\n" for i in range(100)))  # régua trocada
    commit(tmp_path)
    r = runner.invoke(app, ["diff", "-b", "main", "-C", str(tmp_path)])
    assert r.exit_code == 1
    assert "dataset de eval alterado sem mudança" in r.stderr


def test_ac_042_dataset_menor_que_min_cases_e_erro(tmp_path):
    project(tmp_path, cases=50)
    assert any("dataset tem 50 casos, menos que min_cases 100" in e for e in core.load(tmp_path).errors)


def test_mean_score(tmp_path):
    ev = ev_with(aggregate="mean_score", threshold={"min": 0.7})
    rep = run_eval(project(tmp_path, ev, plan=lines_for([0.8, 0.75, 0.7], field="score")))
    row = rep["evals"][0]
    assert row["verdict"] == "OK" and row["value"] == 0.75 and "ci95" not in row


def test_harness_quebrado_reprova(tmp_path):
    project(tmp_path)
    (tmp_path / "harness.py").write_text(encoding="utf-8", data="raise SystemExit(4)")
    rep = run_eval(tmp_path)
    assert not rep["ok"] and "harness saiu com código 4" in rep["problems"]


def test_sem_command_reprova(tmp_path):
    rep = run_eval(project(tmp_path, harness=False))
    assert not rep["ok"] and "evals.command não configurado" in rep["problems"][0]


def test_sem_evals_aprova(tmp_path):
    project(tmp_path)
    f = tmp_path / "specs/features/FEATURE-001/spec.yaml"
    spec = yaml.safe_load(f.read_text(encoding="utf-8"))
    spec.pop("evals")
    f.write_text(encoding="utf-8", data=yaml.safe_dump(spec))
    rep = run_eval(tmp_path)
    assert rep["ok"] is True and rep["evals"] == []


def test_harness_quebrado_via_cli_guarda_final_da_saida(tmp_path):
    project(tmp_path)
    (tmp_path / "harness.py").write_text(encoding="utf-8", data="print('x' * 9000 + 'CAUSA'); raise SystemExit(3)")
    r = runner.invoke(app, ["eval", "-C", str(tmp_path)])
    assert r.exit_code == 1
    saved = json.loads((tmp_path / ".sdd/eval.json").read_text(encoding="utf-8"))["harness"]
    assert saved["exit_code"] == 3
    assert len(saved["output"]) == 4000 and saved["output"].rstrip().endswith("CAUSA")


def test_ac_055_harness_que_estoura_timeout(tmp_path):
    project(tmp_path)
    cfg_file = tmp_path / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg["evals"]["timeout"] = 1
    cfg_file.write_text(encoding="utf-8", data=yaml.safe_dump(cfg))
    (tmp_path / "harness.py").write_text(encoding="utf-8", data="import time; time.sleep(5)")
    rep = run_eval(tmp_path)
    assert rep["harness"]["exit_code"] == -1
    assert "harness excedeu 1s" in rep["harness"]["output"]


def test_juiz_deterministico_nao_mostra_aviso(tmp_path):
    md = evals.render_markdown(run_eval(project(tmp_path)))
    assert "determinístico" in md and "probabilístico" not in md


def test_wilson_conhecido():
    lo, hi = evals.wilson(90, 100)
    assert round(lo, 3) == 0.826 and round(hi, 3) == 0.945
    assert evals.wilson(0, 0) == (0.0, 1.0)


def test_lower_bound_exige_pass_rate():
    import pytest
    with pytest.raises(ValueError):
        Eval(**ev_with(aggregate="mean_score", use_lower_bound=True))
