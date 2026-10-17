"""Offline RAG fixture: real retrieval/ACL/cache logic, no language model or network."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Limits:
    max_calls: int = 3
    max_steps: int = 4
    deadline_ms: float = 1000
    max_cost_usd: float = 0


def audit(trace: dict, limits: Limits) -> list[str]:
    """Checks observed records, not the trustworthiness/completeness of the emitter."""
    errors = []
    spans = trace["spans"]
    calls = [s["operation"] in {"retrieve", "primary", "fallback"} for s in spans]
    if any(s["call"] is not expected for s, expected in zip(spans, calls)):
        errors.append("call_accounting")
    if len(spans) > limits.max_steps or sum(calls) > limits.max_calls:
        errors.append("work_budget")
    import math
    duration = trace["duration_ms"]
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0 or duration > limits.deadline_ms:
        errors.append("deadline")
    costs = [s["cost_usd"] for s in spans]
    if any(type(c) not in (int, float) or not math.isfinite(c) or c < 0 for c in costs) or sum(costs) > limits.max_cost_usd:
        errors.append("cost_budget")
    operations = [s["operation"] for s in spans]
    if any(op not in {"retrieve", "primary", "fallback", "cache", "cancel"} for op in operations):
        errors.append("forbidden_operation")
    if any(s["tenant"] != trace["tenant"] for s in spans):
        errors.append("tenant_scope")
    if any(op in operations for op in ("primary", "fallback")):
        if "retrieve" not in operations or operations.index("retrieve") > min(
                i for i, op in enumerate(operations) if op in {"primary", "fallback"}):
            errors.append("generation_without_retrieval")
    if "cancel" in operations and operations.index("cancel") != len(operations) - 1:
        errors.append("action_after_cancel")
    if "fallback" in operations:
        if "primary" not in operations or operations.index("primary") > operations.index("fallback"):
            errors.append("fallback_without_primary")
        elif spans[operations.index("primary")]["status"] != "error":
            errors.append("fallback_without_failure")
    return errors


class Rag:
    def __init__(self, documents: list[dict]):
        self.documents = documents
        self.cache = {}

    def answer(self, question: str, tenant: str, allowed: list[str], *, primary_down=False,
               fallback_down=False, cancelled=False, limits=Limits()) -> dict:
        started = time.perf_counter()
        spans = []
        trace = {"tenant": tenant, "question_sha256": fingerprint(question), "spans": spans,
                 "duration_ms": 0.0, "billing": "offline_fixture_no_billable_calls"}

        def elapsed():
            return (time.perf_counter() - started) * 1000

        def step(operation, status="ok"):
            if elapsed() > limits.deadline_ms:
                raise RuntimeError("deadline")
            if len(spans) >= limits.max_steps or sum(s["call"] for s in spans) + (operation in {"retrieve", "primary", "fallback"}) > limits.max_calls:
                raise RuntimeError("work_budget")
            spans.append({"operation": operation, "tenant": tenant, "status": status,
                          "call": operation in {"retrieve", "primary", "fallback"}, "cost_usd": 0.0})

        def finish(answer, citations, retrieved):
            trace["duration_ms"] = elapsed()
            errors = audit(trace, limits)
            if errors:
                raise RuntimeError(",".join(errors))
            return {"answer": answer, "citations": citations, "retrieved": retrieved, "trace": trace}

        if cancelled:
            step("cancel", "cancelled")
            return finish(None, [], [])

        # The current corpus and permission set participate in the key, so changes,
        # deletion and revocation invalidate cached answers, including tenant scope.
        key = fingerprint([tenant, sorted(allowed), self.documents, question])
        if key in self.cache:
            step("cache")
            value = self.cache[key]
            return finish(value["answer"], value["citations"], value["retrieved"])
        step("retrieve")
        tokens = set(question.casefold().split())
        visible = [d for d in self.documents if d["active"] and d["tenant"] == tenant and d["id"] in allowed]
        ranked = sorted(visible, key=lambda d: (-len(tokens & set(d["keywords"])), d["id"]))
        selected = [d for d in ranked if tokens & set(d["keywords"])][:1]
        retrieved = [d["id"] for d in selected]
        if not selected:
            return finish(None, [], retrieved)
        step("primary", "error" if primary_down else "ok")
        if primary_down:
            step("fallback", "error" if fallback_down else "ok")
            if fallback_down:
                return finish(None, [], retrieved)
        # Fixture renderer quotes the retrieved source. It does not simulate LLM quality.
        doc = selected[0]
        value = {"answer": doc["text"], "citations": [{"id": doc["id"], "version": doc["version"]}],
                 "retrieved": retrieved}
        result = finish(**value)
        self.cache[key] = value
        return result
