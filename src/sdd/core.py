"""Motor de verificação: determinístico, sem LLM."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import AgentsProfile, ArchRule, Architecture, Config, Decision, DecisionLog, Spec

CONFIG_PATH = "specs/sdd.yaml"
DECISIONS_PATH = "specs/decisions.yaml"
ARCH_PATH = "specs/architecture.yaml"
FEATURES_GLOB = "specs/features/*/spec.yaml"
PLACEHOLDER = "PREENCHER"  # marcador do esqueleto gerado por `sdd specify`
# ID de critério dentro do nome de um teste. Aceita as convenções reais de cada ecossistema:
#   test_ac_001_x (pytest) · "AC-001 cria" (jest/vitest) · TestAC_001_X e TestAC001X (Go,
#   onde o prefixo Test é obrigatório) · testAC001 / shouldX_AC_001 (JUnit) · Sub/AC-003_x.
# Evita falsos positivos como MAC-001, HVAC100, track_001: antes de "AC" vem um não-letra,
# ou uma minúscula/dígito seguida de "AC" maiúsculo (fronteira de CamelCase).
ID_IN_TEST = re.compile(
    r"(?:(?<![A-Za-z])(?P<a>(?i:ac|nfr))|(?<=[a-z0-9])(?P<b>AC|NFR))[-_]?(?P<n>\d{3,})")


@dataclass
class Project:
    root: Path
    config: Config | None = None
    specs: dict[str, Spec] = field(default_factory=dict)  # caminho relativo -> spec
    decisions: dict[str, Decision] = field(default_factory=dict)
    arch: list[ArchRule] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    agents: "AgentsProfile | None" = None


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _fmt(path: str, exc: ValidationError) -> list[str]:
    return [
        f"{path}: {'.'.join(str(p) for p in e['loc']) or '<raiz>'}: {e['msg']}"
        for e in exc.errors()
    ]


def load(root: Path) -> Project:
    """Carrega e valida config + specs. Erros ficam em project.errors."""
    proj = Project(root=root)
    cfg_file = root / CONFIG_PATH
    if not cfg_file.exists():
        proj.errors.append(f"{CONFIG_PATH}: não encontrado (rode `sdd init`)")
    else:
        try:
            proj.config = Config.model_validate(_load_yaml(cfg_file))
        except ValidationError as exc:
            proj.errors += _fmt(CONFIG_PATH, exc)
        except yaml.YAMLError as exc:
            proj.errors.append(f"{CONFIG_PATH}: YAML inválido: {exc}")

    dec_file = root / DECISIONS_PATH
    if dec_file.exists():
        try:
            log = DecisionLog.model_validate(_load_yaml(dec_file) or {})
            for d in log.decisions:
                if d.id in proj.decisions:
                    proj.errors.append(f"{DECISIONS_PATH}: decisão {d.id} duplicada")
                proj.decisions[d.id] = d
            for d in log.decisions:
                if d.superseded_by and d.superseded_by not in proj.decisions:
                    proj.errors.append(f"{DECISIONS_PATH}: {d.id} superseded_by {d.superseded_by} inexistente")
        except ValidationError as exc:
            proj.errors += _fmt(DECISIONS_PATH, exc)
        except yaml.YAMLError as exc:
            proj.errors.append(f"{DECISIONS_PATH}: YAML inválido: {exc}")

    arch_file = root / ARCH_PATH
    if arch_file.exists():
        try:
            proj.arch = Architecture.model_validate(_load_yaml(arch_file) or {}).rules
        except ValidationError as exc:
            proj.errors += _fmt(ARCH_PATH, exc)
        except yaml.YAMLError as exc:
            proj.errors.append(f"{ARCH_PATH}: YAML inválido: {exc}")
    arch_ids: set[str] = set()
    for rule in proj.arch:
        if rule.id in arch_ids:
            proj.errors.append(f"{ARCH_PATH}: regra {rule.id} duplicada")
        arch_ids.add(rule.id)

    files = sorted(root.glob(FEATURES_GLOB))
    if not files:
        proj.errors.append(f"nenhuma spec em {FEATURES_GLOB}")
    for f in files:
        rel = f.relative_to(root).as_posix()
        proj.errors += _placeholders(rel, f.read_text(encoding="utf-8"))
        try:
            proj.specs[rel] = Spec.model_validate(_load_yaml(f))
        except ValidationError as exc:
            proj.errors += _fmt(rel, exc)
        except yaml.YAMLError as exc:
            proj.errors.append(f"{rel}: YAML inválido: {exc}")

    # Regras entre arquivos: IDs únicos no projeto, gates definidos.
    seen: dict[str, str] = {}
    features: dict[str, str] = {}
    for rel, spec in proj.specs.items():
        if spec.feature in features:
            proj.errors.append(f"{rel}: feature '{spec.feature}' duplicada (já em {features[spec.feature]})")
        features[spec.feature] = rel
        crit_ids = [c[0] for c in spec.criteria()] + [e.id for e in spec.evals]
        for i in [r.id for r in spec.requirements] + crit_ids:
            if i in seen:
                proj.errors.append(f"{rel}: ID {i} duplicado (já em {seen[i]})")
            seen[i] = rel
        if proj.config:
            for g in spec.quality_gates:
                if g not in proj.config.gates:
                    proj.errors.append(f"{rel}: gate '{g}' não definido em {CONFIG_PATH}")
            if (proj.config.require_design and spec.design is None
                    and spec.size in proj.config.design_required_for):
                proj.errors.append(f"{rel}: seção `design` obrigatória para size '{spec.size}'")
        for q in spec.open_questions:
            if not q.answer.strip():
                proj.errors.append(f"{rel}: pergunta aberta sem resposta: {q.question}")
        for ref in spec.decisions:
            d = proj.decisions.get(ref)
            if d is None:
                proj.errors.append(f"{rel}: decisão {ref} não existe em {DECISIONS_PATH}")
            elif d.status == "superseded":
                proj.errors.append(f"{rel}: decisão {ref} foi substituída por {d.superseded_by}")
        if spec.design:
            for k, risk in enumerate(spec.design.risks):
                for ref in risk.mitigated_by:
                    if ref not in crit_ids and ref not in arch_ids:
                        proj.errors.append(
                            f"{rel}: design.risks.{k}: mitigated_by '{ref}' não é AC, NFR ou EVAL "
                            f"desta spec nem regra ARCH do projeto")
            for dep in spec.design.dependencies:
                for ref in dep.covered_by:
                    if ref not in crit_ids:
                        proj.errors.append(
                            f"{rel}: dependência '{dep.name}': covered_by '{ref}' não é AC, NFR "
                            f"nem EVAL desta spec")
        for ev in spec.evals:
            if ev.judge == "llm" and proj.config and not proj.config.evals.allow_llm_judge:
                proj.errors.append(
                    f"{rel}: {ev.id} usa judge: llm, mas evals.allow_llm_judge é false em {CONFIG_PATH}")
            ids, err = dataset_ids(root / ev.dataset)
            if err:
                proj.errors.append(f"{rel}: {ev.id}: dataset {ev.dataset}: {err}")
            elif len(ids) < ev.min_cases:
                proj.errors.append(
                    f"{rel}: {ev.id}: dataset tem {len(ids)} casos, menos que min_cases {ev.min_cases}")
    _load_agents(proj)
    return proj


def _placeholders(rel: str, text: str) -> list[str]:
    return [f"{rel}:{n}: campo ainda marcado com {PLACEHOLDER}: {line.strip()}"
            for n, line in enumerate(text.splitlines(), 1)
            if PLACEHOLDER + ":" in line]  # o esqueleto sempre usa "PREENCHER: ..."; prosa não conta


def _load_agents(proj: Project) -> None:
    """Perfil de agentes (specs/agents.yaml), quando o projeto o adota."""
    from .profile import AGENTS_PATH, validate as validate_profile

    f = proj.root / AGENTS_PATH
    if not f.exists():
        return
    text = f.read_text(encoding="utf-8")
    proj.errors += _placeholders(AGENTS_PATH, text)
    try:
        proj.agents = AgentsProfile.model_validate(yaml.safe_load(text) or {})
    except ValidationError as exc:
        proj.errors += _fmt(AGENTS_PATH, exc)
        return
    except yaml.YAMLError as exc:
        proj.errors.append(f"{AGENTS_PATH}: YAML inválido: {exc}")
        return
    errors, warnings = validate_profile(proj, proj.agents)
    proj.errors += errors
    proj.warnings += warnings
    for rel, spec in proj.specs.items():  # N-03/N-07: todo desenho de agente declara limites
        if spec.design and spec.design.limits is None:
            proj.errors.append(f"{rel}: projeto com perfil de agentes: design.limits é obrigatório "
                               "(deadline, etapas, chamadas de ferramenta, custo)")


def dataset_ids(path: Path) -> tuple[set[str], str | None]:
    """IDs de um dataset JSONL (uma linha por caso, cada uma com "id" único)."""
    if not path.is_file():
        return set(), "não encontrado"
    ids: set[str] = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return set(), f"linha {n} não é JSON"
        cid = obj.get("id") if isinstance(obj, dict) else None
        if cid is None:
            return set(), f"linha {n} sem campo \"id\""
        if str(cid) in ids:
            return set(), f"id {cid} duplicado"
        ids.add(str(cid))
    return ids, None


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

    cfg = proj.config
    assert cfg is not None
    problems: list[str] = []

    arch_report = arch.check(proj)
    problems += arch_report["problems"]
    problems += [f"{v['rule']}: {v['file']}:{v['line']} importa '{v['import']}'"
                 for v in arch_report["violations"]]

    junit_path = proj.root / cfg.tests.junit
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    junit_path.unlink(missing_ok=True)  # nunca aceitar evidência de execução anterior
    test_rc, test_out = run(cfg.tests.command, proj.root, cfg.tests.timeout)

    junit: dict = {}
    if junit_path.exists():
        try:
            junit = parse_junit(junit_path)
        except ET.ParseError as exc:
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
    needed = sorted({g for s in proj.specs.values() for g in s.quality_gates})
    for g in needed:
        rc, out = run(cfg.gates[g], proj.root, cfg.tests.timeout)
        gates.append({"gate": g, "command": cfg.gates[g], "ok": rc == 0, "output": out if rc else ""})
        if rc != 0:
            problems.append(f"gate '{g}' falhou (código {rc})")

    return {
        "ok": not problems, "problems": problems, "criteria": rows, "gates": gates,
        "risks": risk_matrix(proj), "architecture": arch_report,
        "dependencies": dependency_matrix(proj),
        "profile": _profile_matrix(proj, rows, arch_report),
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
    violated = {v["rule"] for v in arch_report.get("violations", [])}
    verdicts.update({rid: ("VIOLADA" if rid in violated else "OK") for rid in arch_report.get("rules", [])})
    return {"stage": proj.agents.stage, "requirements": matrix(proj, proj.agents, verdicts)}


def dependency_matrix(proj: Project) -> list[dict]:
    out = []
    for spec in proj.specs.values():
        if spec.design:
            for d in spec.design.dependencies:
                out.append({"feature": spec.feature, **d.model_dump()})
    return out


def render_markdown(report: dict) -> str:
    verdicts = {r["id"]: r["verdict"] for r in report["criteria"]}
    out = ["# Relatório de conformidade SDD", "",
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
        violated = {v["rule"] for v in arch_rep.get("violations", [])}
        for rule_id in arch_rep.get("rules", []):
            verdicts[rule_id] = "VIOLADA" if rule_id in violated else "OK"
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


def write_report(proj: Project, report: dict) -> Path:
    d = proj.root / ".sdd"
    d.mkdir(exist_ok=True)
    (d / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md = d / "report.md"
    md.write_text(render_markdown(report), encoding="utf-8")
    return md
