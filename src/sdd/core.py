"""Execução e agregação de verificação. O carregamento vive em project."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from .artifacts import ArtifactError, confined
from .evidence import architecture_verdicts

# Compatibilidade pública: callers existentes continuam usando core.load/Project.
from .project import Project, load, dataset_ids, CONFIG_PATH, DECISIONS_PATH, ARCH_PATH, FEATURES_GLOB, PLACEHOLDER, ID_IN_TEST

def parse_junit(path: Path) -> dict[str, list[tuple[str, str]]]:
    """ID (AC/NFR) -> [(nome do teste, status)], status em passed/failed/skipped."""
    found: dict[str, list[tuple[str, str]]] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        name = case.get("name", "")
        full = f"{case.get('classname', '')}::{name}"
        tags = {c.tag for c in case}
        status = "failed" if tags & {"failure", "error"} else "skipped" if "skipped" in tags else "passed"
        for kind, num in {((m["a"] or m["b"]).upper(), m["n"]) for m in ID_IN_TEST.finditer(name)}:
            found.setdefault(f"{kind}-{num}", []).append((full, status))
    return found


def trace(proj: Project, junit: dict[str, list[tuple[str, str]]]) -> list[dict]:
    """Uma linha por critério (AC ou NFR), com veredito."""
    rows = []
    for spec in proj.specs.values():
        for cid, origin, text in spec.criteria():
            tests = junit.get(cid, [])
            statuses = {s for _, s in tests}
            if not tests:
                verdict = "SEM_TESTE"
            elif "failed" in statuses:
                verdict = "FALHOU"
            elif statuses == {"skipped"}:
                verdict = "PULADO"
            else:
                verdict = "OK"
            rows.append({
                "feature": spec.feature, "origin": origin, "id": cid,
                "text": text, "verdict": verdict,
                "tests": [{"name": n, "status": s} for n, s in tests],
            })
    return rows


def orphans(proj: Project, junit: dict) -> list[str]:
    """IDs citados em testes que não existem em nenhuma spec."""
    known = {c[0] for s in proj.specs.values() for c in s.criteria()}
    return sorted(set(junit) - known)


def run(cmd: str, root: Path, timeout: int = 3600) -> tuple[int, str]:
    """Roda um comando de shell. Estouro de timeout vira código -1, nunca um travamento."""
    from .procs import run_shell

    r = run_shell(cmd, root, timeout)
    if r.timed_out:
        return -1, f"comando excedeu o timeout de {timeout}s: {cmd}"
    return r.returncode, r.output[-4000:]


def check(proj: Project) -> dict:
    """Roda arquitetura, testes e gates e devolve o relatório. Pressupõe proj sem erros."""
    from . import arch
    from .report import metadata

    cfg = proj.config
    def failed(problems):
        return {**metadata("check"), "ok": False, "problems": problems, "criteria": [],
                "gates": [], "architecture": None, "profile": None, "constitution": None,
                "tests": {"command": cfg.tests.command if cfg else None, "exit_code": None, "output": ""}}

    if proj.errors or cfg is None:
        return failed(proj.errors or ["configuração ausente"])
    problems: list[str] = []

    arch_report = arch.check(proj)
    problems += arch_report["problems"]
    problems += [f"{v['rule']}: {v['file']}:{v['line']} importa '{v['import']}'"
                 for v in arch_report["violations"]]

    try:
        junit_path = confined(proj.root, cfg.tests.junit)
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        junit_path.unlink(missing_ok=True)  # nunca aceitar evidência de execução anterior
    except (OSError, ArtifactError) as exc:
        return failed([f"caminho JUnit inseguro: {exc}"])
    test_rc, test_out = run(cfg.tests.command, proj.root, cfg.tests.timeout)

    junit: dict = {}
    if junit_path.exists():
        try:
            junit = parse_junit(junit_path)
        except (ET.ParseError, OSError, UnicodeError) as exc:
            problems.append(f"JUnit ilegível em {cfg.tests.junit}: {exc}")
    else:
        problems.append(f"comando de testes não gerou {cfg.tests.junit}")

    rows = trace(proj, junit)
    for r in rows:
        if r["verdict"] != "OK":
            problems.append(f"{r['id']} ({r['feature']}): {r['verdict']}")
    for o in orphans(proj, junit):
        problems.append(f"{o}: citado em teste mas ausente das specs")
    if test_rc == -1:
        problems.append(f"suíte de testes excedeu o timeout de {cfg.tests.timeout}s")
    elif test_rc != 0:
        problems.append(f"suíte de testes saiu com código {test_rc}")

    gates = []
    needed = {g for s in proj.specs.values() for g in s.quality_gates}
    if proj.constitution:  # gates que cobram princípios da constituição também rodam
        needed |= {r[5:] for p in proj.constitution.principles for r in p.enforced_by
                   if r.startswith("gate:")}
    needed = sorted(needed)
    for g in needed:
        rc, out = run(cfg.gates[g], proj.root, cfg.tests.timeout)
        gates.append({"gate": g, "command": cfg.gates[g], "ok": rc == 0, "output": out if rc else ""})
        if rc != 0:
            problems.append(f"gate '{g}' falhou (código {rc})")

    verdicts = {r["id"]: r["verdict"] for r in rows}
    verdicts.update(architecture_verdicts(arch_report))
    task_rows = []
    for spec in proj.specs.values():
        for task in spec.tasks:
            ev = [{"id": r, "verdict": verdicts.get(r, "ver sdd eval" if r.startswith("EVAL-") else "?")}
                  for r in task.evidence]
            bad = [e["id"] for e in ev if e["verdict"] not in ("OK", "ver sdd eval")]
            if task.status == "done" and bad:
                problems.append(f"{task.id} ({spec.feature}) marcada como done, mas a evidência não passa: "
                                + ", ".join(f"{e['id']} {e['verdict']}" for e in ev if e["id"] in bad))
            task_rows.append({"feature": spec.feature, "id": task.id, "title": task.title,
                              "status": task.status, "origin": task.origin, "evidence": ev})

    return {
        **metadata("check"),
        "ok": not problems, "problems": problems, "criteria": rows, "gates": gates,
        "risks": risk_matrix(proj), "architecture": arch_report,
        "dependencies": dependency_matrix(proj),
        "profile": _profile_matrix(proj, rows, arch_report),
        "tasks": task_rows,
        "constitution": _constitution_matrix(proj, rows, arch_report, gates, not problems),
        "tests": {"command": cfg.tests.command, "exit_code": test_rc,
                  "output": test_out if test_rc else ""},
    }


def risk_matrix(proj: Project) -> list[dict]:
    """Riscos declarados, com o estado da mitigação preenchido depois pelo check."""
    out = []
    for spec in proj.specs.values():
        if spec.design:
            for r in spec.design.risks:
                out.append({"feature": spec.feature, "area": r.area, "severity": r.severity,
                            "description": r.description, "mitigated_by": r.mitigated_by,
                            "accepted": r.accepted})
    return out


def _profile_matrix(proj: Project, rows: list[dict], arch_report: dict) -> dict | None:
    if proj.agents is None:
        return None
    from .profile import matrix

    verdicts = {r["id"]: r["verdict"] for r in rows}
    verdicts.update(architecture_verdicts(arch_report))
    return {"stage": proj.agents.stage, "requirements": matrix(proj, proj.agents, verdicts)}


def _constitution_matrix(proj: Project, rows: list[dict], arch_report: dict, gates: list[dict], ok: bool):
    if proj.constitution is None:
        return None
    from .analysis import constitution_matrix, kit_context

    verdicts = {r["id"]: r["verdict"] for r in rows}
    verdicts.update(architecture_verdicts(arch_report))
    prof = _profile_matrix(proj, rows, arch_report) or {"requirements": []}
    states = {r["id"]: ("PENDENTE" if r["state"] == "COBERTO" and
                        any(e["verdict"] != "OK" for e in r["evidence"]) else r["state"])
              for r in prof["requirements"]}
    completed = {"check": "OK" if ok else "FALHOU"}
    if arch_report.get("rules"):
        completed["arch"] = "OK" if arch_report["ok"] else "FALHOU"
    return constitution_matrix(proj.constitution, verdicts, {g["gate"]: g["ok"] for g in gates}, states,
                               kit_context(proj, completed))


def dependency_matrix(proj: Project) -> list[dict]:
    out = []
    for spec in proj.specs.values():
        if spec.design:
            for d in spec.design.dependencies:
                out.append({"feature": spec.feature, **d.model_dump()})
    return out


from .report import render_markdown, write_report  # noqa: E402,F401  (compatibilidade)
