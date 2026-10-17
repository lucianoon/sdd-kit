"""Example harness, integrity-checked comparison inputs and local benchmark; not a new sdd API."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path

from sdd.artifacts import atomic_write, confined, parse_json
from pipeline import Limits, Rag, audit

ROOT = Path(__file__).resolve().parent
INPUTS = ("cases.jsonl", "documents.json", "config.json", "prompt.txt", "pipeline.py", "evaluate.py")
METRICS = {"EVAL-001": "outcome", "EVAL-002": "retrieval", "EVAL-003": "trajectory", "EVAL-004": "citations"}


def hashes(root):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in INPUTS}


def write(root, path, value):
    return atomic_write(root, path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def jsonl(values):
    return "".join(json.dumps(v, ensure_ascii=False, allow_nan=False) + "\n" for v in values)


def percentile95(values):
    if not values or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("invalid latency samples")
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def run(root=ROOT, out=".sdd/evals", runs=3):
    if not out.startswith(".sdd/") or runs < 1:
        raise ValueError("use --out .sdd/<nome> e --runs >= 1")
    confined(root, out)
    before = hashes(root)
    cases = [parse_json(line) for line in (root / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [c["id"] for c in cases]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("dataset vazio ou IDs duplicados")
    documents = parse_json((root / "documents.json").read_text(encoding="utf-8"))
    config = parse_json((root / "config.json").read_text(encoding="utf-8"))
    declared = {"provider": "offline-fixture", "model": "source-quote-v1",
                "judge": "deterministic-exact-match-v1", "retrieval": "lexical-top1-v1"}
    if set(config) != set(declared) | {"limits"} or any(config.get(k) != v for k, v in declared.items()):
        raise ValueError("this harness only implements the declared offline fixture")
    limits = Limits(**config["limits"])
    records, traces = [], []
    for iteration in range(1, runs + 1):
        for case in cases:
            # Each case/run starts cold: outage cases cannot be masked by another case's cache.
            engine = Rag(documents)
            result = engine.answer(case["question"], case["tenant"], case["allowed"], limits=limits,
                                   primary_down=case.get("primary_down", False), fallback_down=case.get("fallback_down", False))
            visible = {d["id"]: d for d in documents if d["active"] and d["tenant"] == case["tenant"] and d["id"] in case["allowed"]}
            valid_citations = all(ref["id"] in visible and ref["version"] == visible[ref["id"]]["version"]
                                  and result["answer"] == visible[ref["id"]]["text"] for ref in result["citations"])
            valid_citations = valid_citations and bool(result["citations"]) == (result["answer"] is not None)
            scores = {"outcome": float(result["answer"] == case["expected"]),
                      "retrieval": float(result["retrieved"] == case["relevant"]),
                      "trajectory": float(not audit(result["trace"], limits)),
                      "citations": float(valid_citations)}
            records.append({"case": case["id"], "run": iteration, "category": case["category"], "scores": scores})
            traces.append({"case": case["id"], "run": iteration, **result["trace"]})
    if hashes(root) != before:
        raise ValueError("inputs changed during evaluation")
    payloads = {"results.jsonl": jsonl(records), "traces.jsonl": jsonl(traces)}
    for name, content in payloads.items():
        atomic_write(root, f"{out}/{name}", content)
    # The ordinary sdd eval reader owns score aggregation and pass/fail thresholds.
    for identity, metric in METRICS.items():
        atomic_write(root, f"{out}/{identity}.jsonl", jsonl(
            {"case": r["case"], "run": r["run"], "score": r["scores"][metric]} for r in records))
    manifest = {"version": 1, "scope": "offline_fixture_not_llm_quality", "inputs": before,
                "config": config, "python": platform.python_version(), "platform": platform.platform(),
                "workload": "sequential cold fixture cases, no concurrency", "runs": runs,
                "cases": {c["id"]: c["category"] for c in cases},
                "artifacts": {name: hashlib.sha256(content.encode("utf-8")).hexdigest() for name, content in payloads.items()}}
    write(root, f"{out}/manifest.json", manifest)
    return manifest


def snapshot(root, folder):
    manifest = parse_json(confined(root, folder + "/manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != 1 or manifest["scope"] != "offline_fixture_not_llm_quality":
        raise ValueError("unsupported snapshot")
    payloads = {}
    for name in ("results.jsonl", "traces.jsonl"):
        content = confined(root, folder + "/" + name).read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest["artifacts"][name]:
            raise ValueError("snapshot artifact changed: " + name)
        payloads[name] = [parse_json(line) for line in content.decode("utf-8").splitlines() if line.strip()]
    if type(manifest["runs"]) is not int or manifest["runs"] < 1 or not manifest["cases"]:
        raise ValueError("empty/invalid snapshot experiment")
    expected = {(case, n) for case in manifest["cases"] for n in range(1, manifest["runs"] + 1)}
    for name, rows in payloads.items():
        keys = [(row["case"], row["run"]) for row in rows]
        if any(type(r["run"]) is not int for r in rows) or len(keys) != len(set(keys)) or set(keys) != expected:
            raise ValueError("snapshot coverage/duplicates: " + name)
    for row in payloads["results.jsonl"]:
        if row["category"] != manifest["cases"][row["case"]] or set(row["scores"]) != set(METRICS.values()):
            raise ValueError("snapshot category/metrics mismatch")
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in row["scores"].values()):
            raise ValueError("invalid score")
    return manifest, payloads


def compare(root, baseline, candidate):
    left, ldata = snapshot(root, baseline)
    right, rdata = snapshot(root, candidate)
    # Changing cases, corpus or judge makes the paired experiment incomparable.
    if (left["cases"] != right["cases"] or left["runs"] != right["runs"]
            or any(left["inputs"][p] != right["inputs"][p] for p in ("cases.jsonl", "documents.json", "evaluate.py"))
            or left["config"]["judge"] != right["config"]["judge"] or left["scope"] != right["scope"]):
        raise ValueError("incomparable dataset, corpus, scorer or run count")
    previous = {(r["case"], r["run"]): r for r in ldata["results.jsonl"]}
    regressions = []
    for row in rdata["results.jsonl"]:
        old = previous[row["case"], row["run"]]
        for metric, value in row["scores"].items():
            if value < old["scores"][metric]:
                regressions.append({"case": row["case"], "run": row["run"], "category": row["category"],
                                    "metric": metric, "before": old["scores"][metric], "after": value})
    changes = [k for k in left["inputs"] if left["inputs"][k] != right["inputs"][k]]
    return {"ok": not regressions, "regressions": regressions, "changed_inputs": changes,
            "config_changed": left["config"] != right["config"],
            "scope": "paired case/run regression check, not a statistical significance test"}


def benchmark(root, folder, max_p95_ms):
    if not math.isfinite(max_p95_ms) or max_p95_ms < 0:
        raise ValueError("invalid latency threshold")
    manifest, data = snapshot(root, folder)
    limits = Limits(**manifest["config"]["limits"])
    errors = [{"case": r["case"], "run": r["run"], "problems": audit(r, limits)}
              for r in data["traces.jsonl"] if audit(r, limits)]
    p95 = percentile95([r["duration_ms"] for r in data["traces.jsonl"]])
    return {"ok": not errors and p95 <= max_p95_ms, "p95_ms": p95, "threshold_ms": max_p95_ms,
            "trace_errors": errors, "ttft_ms": None, "scope": "local fixture latency, cold cases; no model latency or throughput claim"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--out", default=".sdd/evals")
    execute.add_argument("--runs", type=int, default=3)
    pairing = commands.add_parser("compare")
    pairing.add_argument("baseline")
    pairing.add_argument("candidate")
    perf = commands.add_parser("benchmark")
    perf.add_argument("folder")
    perf.add_argument("--max-p95-ms", type=float, required=True)
    args = parser.parse_args()
    try:
        if args.command == "run":
            report = run(out=args.out, runs=args.runs)
        elif args.command == "compare":
            report = compare(ROOT, args.baseline, args.candidate)
        else:
            report = benchmark(ROOT, args.folder, args.max_p95_ms)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if report.get("ok", True) else 1
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
