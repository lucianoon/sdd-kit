"""Interpretação única de resultados por regra; declaração nunca é execução."""
from __future__ import annotations


def architecture_verdicts(report: dict) -> dict[str, str]:
    if "rule_results" in report:
        return dict(report["rule_results"])
    # Compatibilidade com relatórios de formato 1 anteriores à matriz por regra.
    violated = {v["rule"] for v in report.get("violations", [])}
    return {rid: "VIOLADA" if rid in violated else "FALHOU" if report.get("problems") else "OK"
            for rid in report.get("rules", [])}
