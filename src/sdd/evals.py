"""Evals: critérios estatísticos para comportamento não determinístico.

O harness (qualquer linguagem) só grava resultados BRUTOS, um por caso e execução.
Agregação, cobertura do dataset, estabilidade entre execuções e intervalo de confiança
são calculados aqui, de forma determinística: o harness não declara a própria nota.
"""
from __future__ import annotations

import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

from .core import Project, dataset_ids
from .procs import run_shell
from .models import Eval
from .report import metadata, version_line, constitution_section

Z95 = 1.959964


def wilson(k: int, n: int) -> tuple[float, float]:
    """Intervalo de confiança de 95% (Wilson) para uma proporção k/n."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + Z95 ** 2 / n
    center = (p + Z95 ** 2 / (2 * n)) / den
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95 ** 2 / (4 * n ** 2)) / den
    return max(0.0, center - half), min(1.0, center + half)


def _row(spec_feature: str, ev: Eval, verdict: str, detail: str = "", **extra) -> dict:
    return {"feature": spec_feature, "id": ev.id, "metric": ev.metric, "judge": ev.judge,
            "aggregate": ev.aggregate, "threshold": ev.threshold.model_dump(exclude_none=True),
            "verdict": verdict, "detail": detail, **extra}


def _finite_score(value) -> bool:
    try:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:  # inteiros que não cabem no float usado na agregação
        return False


def evaluate(feature: str, ev: Eval, known: set[str], results: Path) -> dict:
    if not results.is_file():
        return _row(feature, ev, "SEM_RESULTADO", f"harness não gerou {results.name}")

    per_run: dict[int, dict[str, dict]] = defaultdict(dict)
    for n, line in enumerate(results.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            case, run = str(r["case"]), int(r["run"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return _row(feature, ev, "INCOMPLETO", f"linha {n}: esperado {{case, run, pass|score}}")
        if case not in known:
            return _row(feature, ev, "INCOMPLETO", f"caso '{case}' não existe no dataset")
        if case in per_run[run]:
            return _row(feature, ev, "INCOMPLETO", f"caso '{case}' duplicado na execução {run}")
        if ev.aggregate == "pass_rate" and not isinstance(r.get("pass"), bool):
            return _row(feature, ev, "INCOMPLETO", f"linha {n}: 'pass' deve ser true/false")
        if ev.aggregate == "mean_score" and not _finite_score(r.get("score")):
            return _row(feature, ev, "INCOMPLETO",
                        f"linha {n}: 'score' deve ser número finito, sem booleanos")
        per_run[run][case] = r

    if len(per_run) < ev.runs:
        return _row(feature, ev, "INCOMPLETO", f"{len(per_run)} execução(ões), exigido {ev.runs}")
    short = {run: len(c) for run, c in per_run.items() if len(c) < ev.min_cases}
    if short:
        run, got = next(iter(sorted(short.items())))
        return _row(feature, ev, "INCOMPLETO", f"execução {run} com {got} casos, exigido {ev.min_cases}")

    key = "pass" if ev.aggregate == "pass_rate" else "score"
    run_values = {run: sum(float(r[key]) for r in cases.values()) / len(cases)
                  for run, cases in sorted(per_run.items())}
    value = sum(run_values.values()) / len(run_values)
    spread = max(run_values.values()) - min(run_values.values())
    if not all(math.isfinite(v) for v in [*run_values.values(), value, spread]):
        return _row(feature, ev, "INCOMPLETO", "agregação de 'score' produziu valor não finito")
    extra = {"value": round(value, 4), "spread": round(spread, 4), "runs": len(run_values),
             "cases_per_run": min(len(c) for c in per_run.values()),
             "run_values": {str(k): round(v, 4) for k, v in run_values.items()}}

    lo = hi = None
    if ev.aggregate == "pass_rate":
        k = sum(bool(r["pass"]) for cases in per_run.values() for r in cases.values())
        n = sum(len(cases) for cases in per_run.values())
        lo, hi = wilson(k, n)
        extra["ci95"] = [round(lo, 4), round(hi, 4)]

    if ev.critical:  # um único caso falho reprova, qualquer que seja a média
        failed = [f"{case} (execução {run})" for run, cases in sorted(per_run.items())
                  for case, r in cases.items() if not r["pass"]]
        if failed:
            shown = ", ".join(failed[:5]) + (" …" if len(failed) > 5 else "")
            return _row(feature, ev, "FALHA_CRITICA", f"{len(failed)} caso(s) falharam: {shown}", **extra)

    t = ev.threshold
    low_side = lo if ev.use_lower_bound else value
    high_side = hi if ev.use_lower_bound else value
    if t.min is not None and low_side < t.min:
        basis = "limite inferior do IC95" if ev.use_lower_bound else "média"
        return _row(feature, ev, "FORA_DO_LIMITE", f"{basis} {low_side:.3f} < mínimo {t.min:g}", **extra)
    if t.max is not None and high_side > t.max:
        basis = "limite superior do IC95" if ev.use_lower_bound else "média"
        return _row(feature, ev, "FORA_DO_LIMITE", f"{basis} {high_side:.3f} > máximo {t.max:g}", **extra)
    if ev.max_run_spread is not None and spread > ev.max_run_spread:
        return _row(feature, ev, "INSTAVEL",
                    f"variação entre execuções {spread:.3f} > {ev.max_run_spread:g}", **extra)
    return _row(feature, ev, "OK", **extra)


def run(proj: Project) -> dict:
    cfg = proj.config.evals
    pairs = [(s, e) for s in proj.specs.values() for e in s.evals]
    report = {**metadata("eval"), "ok": True, "problems": [], "evals": [], "harness": None,
              "probabilistic": any(e.judge == "llm" for _, e in pairs)}
    if not pairs:
        return report
    if not cfg.command:
        report.update(ok=False, problems=["evals.command não configurado em specs/sdd.yaml"])
        return report

    out_dir = proj.root / cfg.results_dir
    shutil.rmtree(out_dir, ignore_errors=True)  # nunca aceitar resultado de execução anterior
    out_dir.mkdir(parents=True)
    r = run_shell(cfg.command, proj.root, cfg.timeout)
    rc, out = r.returncode, r.output[-4000:]
    if r.timed_out:
        out = f"harness excedeu {cfg.timeout}s"
    report["harness"] = {"command": cfg.command, "exit_code": rc, "output": out if rc else ""}
    if rc != 0:
        report["problems"].append(f"harness saiu com código {rc}")

    for spec, ev in pairs:
        known, _ = dataset_ids(proj.root / ev.dataset)
        row = evaluate(spec.feature, ev, known, out_dir / f"{ev.id}.jsonl")
        report["evals"].append(row)
        if row["verdict"] != "OK":
            report["problems"].append(f"{ev.id} ({spec.feature}): {row['verdict']} {row['detail']}".rstrip())
    report["ok"] = not report["problems"]
    return report


def render_markdown(report: dict) -> str:
    tag = " (evidência probabilística)" if report.get("probabilistic") else ""
    out = ["# Relatório de evals SDD", "", version_line(report), "",
           f"**Resultado: {'APROVADO' if report['ok'] else 'REPROVADO'}{tag}**", "",
           "| Feature | Eval | Métrica | Valor | IC 95% | Variação | Limite | Juiz | Veredito |",
           "|---|---|---|---|---|---|---|---|---|"]
    llm = False
    for r in report["evals"]:
        lim = " e ".join(f"{'≥' if k == 'min' else '≤'} {v:g}" for k, v in r["threshold"].items())
        ci = "–".join(f"{x:.3f}" for x in r["ci95"]) if r.get("ci95") else "—"
        val = f"{r['value']:.3f}" if "value" in r else "—"
        spread = f"{r['spread']:.3f}" if "spread" in r else "—"
        judge = "LLM ⚠" if r["judge"] == "llm" else "determinístico"
        llm |= r["judge"] == "llm"
        verdict = r["verdict"] + (f": {r['detail']}" if r["detail"] else "")
        out.append(f"| {r['feature']} | {r['id']} | {r['metric']} | {val} | {ci} | {spread} | "
                   f"{lim} | {judge} | {verdict} |")
    if llm:
        out += ["", "⚠ **Juiz LLM:** nestes evals o `pass` de cada caso foi decidido por um modelo. "
                "O sdd agrega de forma determinística, mas o veredito de cada caso é probabilístico. "
                "Trate como evidência, não como prova; revise uma amostra manualmente."]
    if report["problems"]:
        out += ["", "## Problemas", ""] + [f"- {p}" for p in report["problems"]]
    out += constitution_section(report.get("constitution"))
    return "\n".join(out) + "\n"
