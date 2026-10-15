"""Análise estática: diagnósticos e rastreio declarados, sem executar o projeto."""
from __future__ import annotations

import hashlib
import json

from .report import metadata, version_line


def _finding(code: str, severity: str, message: str, sources: list[str]) -> dict:
    key = json.dumps([code, message, sources])
    return {"id": "F-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
            "code": code, "severity": severity, "message": message, "sources": sources}


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def analyze(proj) -> dict:
    findings = []
    for severity, messages in (("ERROR", proj.errors), ("WARNING", proj.warnings)):
        for message in sorted(set(messages)):
            source = message.split(":", 1)[0]
            findings.append(_finding("VALIDATION", severity, message,
                                     [source] if source.startswith("specs/") else []))

    coverage = []
    scenarios: dict[tuple, list[dict]] = {}
    for path, spec in sorted(proj.specs.items()):
        for req in spec.requirements:
            for ac in req.acceptance:
                key = tuple(_normalize(v) for v in (ac.given, ac.when, ac.then)) + (
                    tuple(sorted({_normalize(v) for v in ac.forbidden})),)
                scenarios.setdefault(key, []).append({"id": ac.id, "source": path})
        criteria = spec.criteria() + [(ev.id, "eval", ev.description or ev.metric) for ev in spec.evals]
        for cid, origin, text in criteria:
            # Mesma regra de cobertura do check_tasks: citar o REQ cobre seus ACs.
            refs = {cid, origin} if origin.startswith("REQ-") else {cid}
            tasks = [{"id": t.id, "status": t.status,
                      "via": sorted(refs.intersection(t.origin + t.evidence))}
                     for t in spec.tasks if refs.intersection(t.origin + t.evidence)]
            coverage.append({"id": cid, "origin": origin, "feature": spec.feature,
                             "source": path, "text": text, "tasks": tasks,
                             "state": "DECLARADO" if tasks else "SEM_TAREFA",
                             "evidence_state": "NÃO_EXECUTADA"})

    for items in scenarios.values():
        if len(items) > 1:
            refs = ", ".join(f"{i['id']} ({i['source']})" for i in items)
            findings.append(_finding("DUPLICATE_SCENARIO", "WARNING",
                                     "cenário de aceitação repetido: " + refs,
                                     sorted({i["source"] for i in items})))
    findings.sort(key=lambda f: (f["severity"] != "ERROR", f["code"], f["id"]))
    return {**metadata("analyze"), "ok": not proj.errors,
            "scope": "análise estática das declarações; testes, gates e evals não executados",
            "summary": {"features": len(proj.specs), "criteria": len(coverage),
                        "criteria_with_tasks": sum(bool(r["tasks"]) for r in coverage),
                        "errors": sum(f["severity"] == "ERROR" for f in findings),
                        "warnings": sum(f["severity"] == "WARNING" for f in findings)},
            "findings": findings, "coverage": coverage}


def render_markdown(report: dict) -> str:
    def cell(value) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    out = ["# Análise de consistência SDD", "", version_line(report), "",
           "**Estado: " + ("SEM ERROS ESTÁTICOS" if report["ok"] else "COM ERROS") + "**", "",
           report["scope"] + ". Isto não aprova a implementação.", "",
           "## Diagnósticos", "", "| ID | Severidade | Tipo | Diagnóstico |",
           "|---|---|---|---|"]
    for f in report["findings"]:
        out.append("| " + " | ".join(cell(f[k]) for k in ("id", "severity", "code", "message")) + " |")
    out += ["", "## Rastreabilidade declarada", "",
            "| Feature | Arquivo | Critério | Origem | Tarefas | Evidência |", "|---|---|---|---|---|---|"]
    for r in report["coverage"]:
        tasks = ", ".join(f"{t['id']} ({t['status']}; via {', '.join(t['via'])})" for t in r["tasks"])
        values = (r["feature"], r["source"], r["id"], r["origin"], tasks or "SEM_TAREFA", r["evidence_state"])
        out.append("| " + " | ".join(cell(v) for v in values) + " |")
    return "\n".join(out) + "\n"
