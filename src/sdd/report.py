"""Relatório de conformidade do `sdd check` (Markdown e JSON)."""
from __future__ import annotations

import json
from pathlib import Path

from .artifacts import atomic_write


def metadata(command: str) -> dict:
    from . import __version__

    return {"report_version": 1, "tool_version": __version__, "command": command}


def version_line(report: dict) -> str:
    if "tool_version" not in report:
        return ""
    return (f"sdd-kit {report['tool_version']} · formato {report['report_version']} "
            f"· comando `{report['command']}`")


def write_command_report(root: Path, command: str, report, markdown: str) -> Path:
    if not command or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in command):
        raise ValueError("nome de relatório inválido")
    payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    atomic_write(root, f".sdd/{command}.json", payload)
    md = atomic_write(root, f".sdd/{command}.md", markdown)
    return md


def constitution_section(rows: list[dict] | None) -> list[str]:
    if not rows:
        return []
    out = ["", "## Constituição", "", "| Princípio | Estado | Evidência |", "|---|---|---|"]
    for c in rows:
        how = ", ".join(f"{r['ref']} ({r['state']})" for r in c["enforced_by"])
        if c["manual"]:
            how += ("; " if how else "") + f"revisão manual: {c['manual']}"
        out.append(f"| {c['id']} {c['rule']} | {c['status']} | {how} |")
    pending = [c["id"] for c in rows if c["status"] in ("PENDENTE", "DECLARADO")]
    if pending:
        out += ["", "Verificações constitucionais pendentes nesta execução: " + ", ".join(pending) + "."]
    return out


def render_markdown(report: dict) -> str:
    verdicts = {r["id"]: r["verdict"] for r in report["criteria"]}
    out = ["# Relatório de conformidade SDD", "", version_line(report), "",
           f"**Resultado: {'APROVADO' if report['ok'] else 'REPROVADO'}**", "",
           "| Feature | Origem | Critério | Descrição | Veredito | Testes |", "|---|---|---|---|---|---|"]
    for r in report["criteria"]:
        tests = "<br>".join(f"`{t['name']}` ({t['status']})" for t in r["tests"]) or "—"
        out.append(f"| {r['feature']} | {r['origin']} | {r['id']} | {r['text']} | {r['verdict']} | {tests} |")
    if report["gates"]:
        out += ["", "| Gate | Comando | Resultado |", "|---|---|---|"]
        out += [f"| {g['gate']} | `{g['command']}` | {'OK' if g['ok'] else 'FALHOU'} |" for g in report["gates"]]
    if report.get("risks"):
        out += ["", "## Riscos", "", "| Feature | Área | Severidade | Risco | Tratamento |", "|---|---|---|---|---|"]
        arch_rep = report.get("architecture") or {}
        from .evidence import architecture_verdicts
        verdicts.update(architecture_verdicts(arch_rep))
        for k in report["risks"]:
            if k["mitigated_by"]:
                how = ", ".join(
                    f"{i} ({'ver sdd eval' if i.startswith('EVAL-') else verdicts.get(i, '?')})"
                    for i in k["mitigated_by"])
            else:
                how = f"aceito: {k['accepted']}"
            out.append(f"| {k['feature']} | {k['area']} | {k['severity']} | {k['description']} | {how} |")
    arch_rep = report.get("architecture") or {}
    if arch_rep.get("rules"):
        out += ["", "## Arquitetura", ""]
        if arch_rep["violations"]:
            out += ["| Regra | Onde | Import proibido |", "|---|---|---|"]
            out += [f"| {v['rule']} | `{v['file']}:{v['line']}` | `{v['import']}` |"
                    for v in arch_rep["violations"]]
        else:
            out.append(f"{len(arch_rep['rules'])} regra(s), {arch_rep['files']} arquivo(s) "
                       "verificado(s), nenhuma violação.")
        if arch_rep["exceptions"]:
            out += ["", "Exceções declaradas no código:", ""]
            out += [f"- {e['rule']} em `{e['file']}:{e['line']}` (`{e['import']}`): {e['reason']}"
                    for e in arch_rep["exceptions"]]
    if report.get("dependencies"):
        out += ["", "## Dependências e modos de falha", "",
                "| Feature | Dependência | Timeout | Tentativas | Efeito colateral | Idempotente | Fallback | Testado por |",
                "|---|---|---|---|---|---|---|---|"]
        for d in report["dependencies"]:
            tested = ", ".join(f"{i} ({verdicts.get(i, 'ver sdd eval')})" for i in d["covered_by"])
            out.append(f"| {d['feature']} | {d['name']} ({d['kind']}) | {d['timeout_ms']} ms | "
                       f"{d['retry']['max_attempts']} | {'sim' if d['side_effects'] else 'não'} | "
                       f"{'sim' if d['idempotent'] else 'não'} | {d['fallback']} | {tested} |")
    out += constitution_section(report.get("constitution"))
    if report.get("tasks"):
        out += ["", "## Tarefas", "", "| Feature | Tarefa | Status | Origem | Evidência |", "|---|---|---|---|---|"]
        for tk in report["tasks"]:
            ev = ", ".join(f"{e['id']} ({e['verdict']})" for e in tk["evidence"]) or "—"
            out.append(f"| {tk['feature']} | {tk['id']} {tk['title']} | {tk['status']} | "
                       f"{', '.join(tk['origin'])} | {ev} |")
    prof = report.get("profile")
    if prof:
        active = [r for r in prof["requirements"] if r["state"] not in ("INATIVO", "PENDENTE", "NÃO DECLARADO")]
        off = sorted({f"{r['module']} ({r['state'].lower()})" for r in prof["requirements"]
                      if r["state"] in ("INATIVO", "PENDENTE", "NÃO DECLARADO")})
        out += ["", f"## Perfil de agentes (estágio {prof['stage']})", "",
                "| Requisito | Estado | Evidências |", "|---|---|---|"]
        for r in active:
            ev = ", ".join(f"{e['id']} ({e['verdict']})" for e in r["evidence"]) or "—"
            star = " *" if r["critical"] else ""
            out.append(f"| {r['id']} {r['title']}{star} | {r['state']} | {ev} |")
        if off:
            out += ["", "Módulos fora do escopo: " + ", ".join(off) + ". (*) requisito crítico."]
    if report["problems"]:
        out += ["", "## Problemas", ""] + [f"- {p}" for p in report["problems"]]
    return "\n".join(out) + "\n"


def write_report(proj, report: dict) -> Path:
    return write_command_report(proj.root, "report", report, render_markdown(report))
