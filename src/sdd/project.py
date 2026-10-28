"""Carregamento e validação de projeto; não executa testes, gates ou harnesses."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import yaml
from pydantic import ValidationError
from .models import AgentsProfile, ArchRule, Architecture, Config, Constitution, Decision, DecisionLog, Spec
from .artifacts import load_yaml, parse_json

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
    constitution: "Constitution | None" = None


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
            proj.config = Config.model_validate(load_yaml(cfg_file))
        except ValidationError as exc:
            proj.errors += _fmt(CONFIG_PATH, exc)
        except (yaml.YAMLError, OSError, UnicodeError, ValueError, RecursionError) as exc:
            proj.errors.append(f"{CONFIG_PATH}: YAML inválido: {exc}")

    dec_file = root / DECISIONS_PATH
    if dec_file.exists():
        try:
            log = DecisionLog.model_validate(load_yaml(dec_file) or {})
            for d in log.decisions:
                if d.id in proj.decisions:
                    proj.errors.append(f"{DECISIONS_PATH}: decisão {d.id} duplicada")
                proj.decisions[d.id] = d
            for d in log.decisions:
                if d.superseded_by and d.superseded_by not in proj.decisions:
                    proj.errors.append(f"{DECISIONS_PATH}: {d.id} superseded_by {d.superseded_by} inexistente")
        except ValidationError as exc:
            proj.errors += _fmt(DECISIONS_PATH, exc)
        except (yaml.YAMLError, OSError, UnicodeError, ValueError, RecursionError) as exc:
            proj.errors.append(f"{DECISIONS_PATH}: YAML inválido: {exc}")

    arch_file = root / ARCH_PATH
    if arch_file.exists():
        try:
            proj.arch = Architecture.model_validate(load_yaml(arch_file) or {}).rules
        except ValidationError as exc:
            proj.errors += _fmt(ARCH_PATH, exc)
        except (yaml.YAMLError, OSError, UnicodeError, ValueError, RecursionError) as exc:
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
        try:
            proj.errors += _placeholders(rel, f.read_text(encoding="utf-8"))
            proj.specs[rel] = Spec.model_validate(load_yaml(f))
        except ValidationError as exc:
            proj.errors += _fmt(rel, exc)
        except (yaml.YAMLError, OSError, UnicodeError, ValueError, RecursionError) as exc:
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
    _load_constitution(proj)
    _analyze(proj)
    return proj


def _load_constitution(proj: Project) -> None:
    from .analysis import CONSTITUTION_PATH, check_constitution

    f = proj.root / CONSTITUTION_PATH
    if not f.exists():
        return
    try:
        proj.constitution = Constitution.model_validate(load_yaml(f) or {})
    except ValidationError as exc:
        proj.errors += _fmt(CONSTITUTION_PATH, exc)
        return
    except (yaml.YAMLError, OSError, UnicodeError, ValueError, RecursionError) as exc:
        proj.errors.append(f"{CONSTITUTION_PATH}: YAML inválido: {exc}")
        return
    proj.errors += check_constitution(proj, proj.constitution)


def _analyze(proj: Project) -> None:
    """Tarefas (origem, dependências, cobertura), critérios vagos, aprovações e dimensões."""
    from .analysis import check_criteria, check_tasks
    from .approvals import problems as approval_problems
    from .dimensions import check as check_dimensions

    global_ids = {r.id for r in proj.arch}
    if proj.constitution:
        global_ids |= {p.id for p in proj.constitution.principles}
    for rel, spec in proj.specs.items():
        cfg = proj.config
        if cfg and cfg.require_tasks and spec.size in cfg.tasks_required_for and not spec.tasks:
            proj.errors.append(f"{rel}: `tasks` obrigatório para size '{spec.size}' (require_tasks: true)")
        proj.errors += check_tasks(rel, spec, global_ids)
        vague = check_criteria(rel, spec)
        if cfg and cfg.strict_criteria:
            proj.errors += vague
        else:
            proj.warnings += vague
        # Aprovação é condição para implementar (AD-008), não validade do contrato: só avisa.
        proj.warnings += approval_problems(rel, spec, cfg) + check_dimensions(rel, spec)


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
    try:
        text = f.read_text(encoding="utf-8")
        proj.errors += _placeholders(AGENTS_PATH, text)
        proj.agents = AgentsProfile.model_validate(load_yaml(f) or {})
    except ValidationError as exc:
        proj.errors += _fmt(AGENTS_PATH, exc)
        return
    except (yaml.YAMLError, OSError, UnicodeError, ValueError, RecursionError) as exc:
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
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return set(), f"não foi possível ler: {exc}"
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = parse_json(line)
        except ValueError:
            return set(), f"linha {n} não é JSON"
        cid = obj.get("id") if isinstance(obj, dict) else None
        if cid is None:
            return set(), f"linha {n} sem campo \"id\""
        if str(cid) in ids:
            return set(), f"id {cid} duplicado"
        ids.add(str(cid))
    return ids, None
