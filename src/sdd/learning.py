"""Reviewed lessons and semantic test reviews, separate from executable evidence."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError
import yaml

from .artifacts import ArtifactError, atomic_write, confined, load_yaml
from .models import Strict
from .project import load


class Citation(Strict):
    path: str
    line: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewItem(Strict):
    criterion: str
    verdict: Literal["pending", "adequate", "partial", "inadequate"] = "pending"
    assertion: str = ""
    detects: str = ""
    evidence: list[Citation] = []


class Adequacy(Strict):
    version: Literal[1] = 1
    feature: str
    spec_sha256: str
    sources: dict[str, str] = {}
    implementer: str = ""
    reviewer: str = ""
    reviewer_kind: Literal["human", "agent"] = "human"
    items: list[ReviewItem]


class Lesson(Strict):
    id: str = Field(pattern=r"^LESSON-\d{3,}$")
    feature: str = "*"
    cause: str = Field(min_length=1)
    prevention: str = Field(min_length=1)
    evidence: list[Citation] = Field(min_length=1)
    status: Literal["proposed", "accepted", "retired"] = "proposed"
    accepted_by: str = ""


class Lessons(Strict):
    version: Literal[1] = 1
    lessons: list[Lesson] = []


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_model(root: Path, path: str, model):
    try:
        return model.model_validate(load_yaml(confined(root, path)))
    except (OSError, UnicodeError, ValueError, yaml.YAMLError, RecursionError) as exc:
        raise ArtifactError(f"{path}: {exc}") from exc


def save(root: Path, path: str, value) -> Path:
    return atomic_write(root, path, yaml.safe_dump(value.model_dump() if hasattr(value, "model_dump") else value,
                                                  sort_keys=False, allow_unicode=True))


def selected(root: Path, feature: str):
    proj = load(root)
    matches = [(p, s) for p, s in proj.specs.items() if s.feature == feature]
    if proj.errors or len(matches) != 1:
        raise ArtifactError("projeto inválido ou feature inexistente/ambígua: " + "; ".join(proj.errors))
    return matches[0]


def slug(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", value):
        raise ArtifactError("nome precisa conter minúsculas, números e hífen")
    return value


def citation(root: Path, value: str) -> Citation:
    try:
        path, line = value.rsplit(":", 1)
        line = int(line)
        target = confined(root, path)
        if line < 1 or line > len(target.read_text(encoding="utf-8").splitlines()):
            raise ValueError("linha inexistente")
        return Citation(path=path, line=line, sha256=digest(target))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ArtifactError(f"referência inválida {value}: {exc}") from exc


def current(root: Path, ref: Citation) -> bool:
    p = confined(root, ref.path)
    return p.is_file() and digest(p) == ref.sha256 and ref.line <= len(p.read_text(encoding="utf-8").splitlines())


def source_hashes(root: Path, spec) -> dict[str, str]:
    result = {}
    for pattern in spec.paths:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                result[rel] = digest(confined(root, rel))
    return result


def template(root: Path, feature: str) -> Path:
    path, spec = selected(root, feature)
    destination = f"specs/reviews/{slug(feature)}.yaml"
    if confined(root, destination).exists():
        raise ArtifactError("revisão existente preservada")
    value = Adequacy(feature=feature, spec_sha256=digest(confined(root, path)), sources=source_hashes(root, spec),
                     items=[ReviewItem(criterion=cid) for cid, _, _ in spec.criteria()])
    return save(root, destination, value)


def human_required(root: Path, spec) -> list[str]:
    """Por que esta feature exige revisor humano na adequação (vazio: não exige)."""
    from .diff import matches
    proj = load(root)
    cfg = proj.config.review if proj.config else None
    why = []
    if cfg and matches(spec.feature, cfg.human_adequacy):
        why.append("feature listada em review.human_adequacy")
    if spec.design and any(r.severity == "high" for r in spec.design.risks):
        why.append("spec com risco high")
    return why


def adequacy(root: Path, feature: str) -> dict:
    path, spec = selected(root, feature)
    review = read_model(root, f"specs/reviews/{slug(feature)}.yaml", Adequacy)
    problems = []
    human = human_required(root, spec)
    if human and review.reviewer_kind != "human":
        problems.append("revisor humano exigido (" + "; ".join(human)
                        + "); revisão de agente não substitui aprovação humana")
    if review.feature != feature or review.spec_sha256 != digest(confined(root, path)):
        problems.append("spec alterada ou feature divergente; revisão desatualizada")
    if not review.implementer.strip() or not review.reviewer.strip() or review.implementer.strip().casefold() == review.reviewer.strip().casefold():
        problems.append("declare implementador e revisor distintos; identidade é declarada, não autenticada")
    if review.sources != source_hashes(root, spec):
        problems.append("fontes da feature alteradas; revisão desatualizada")
    wanted = {cid for cid, _, _ in spec.criteria()}
    ids = [item.criterion for item in review.items]
    if len(ids) != len(set(ids)) or set(ids) != wanted:
        problems.append("critérios duplicados, ausentes ou desconhecidos")
    for item in review.items:
        if item.verdict != "adequate" or not item.assertion.strip() or not item.detects.strip() or not item.evidence:
            problems.append(f"{item.criterion}: adequação pendente ou insuficiente")
        for ref in item.evidence:
            if not current(root, ref):
                problems.append(f"{item.criterion}: evidência desatualizada {ref.path}:{ref.line}")
    return {"command": "adequacy", "report_version": 1, "feature": feature, "ok": not problems,
            "scope": "integridade da revisão declarada; não executa testes nem comprova equivalência semântica",
            "reviewer_kind": review.reviewer_kind, "human_required": human,
            "evidence": "humana declarada" if review.reviewer_kind == "human" else "probabilística",
            "problems": problems, "review": review.model_dump()}


def lessons(root: Path) -> Lessons:
    path = confined(root, "specs/lessons.yaml")
    result = read_model(root, "specs/lessons.yaml", Lessons) if path.exists() else Lessons()
    ids = [v.id for v in result.lessons]
    if len(ids) != len(set(ids)):
        raise ArtifactError("IDs de lições duplicados")
    return result


def add_lesson(root: Path, feature: str, cause: str, prevention: str, refs: list[str]) -> Lesson:
    if feature != "*":
        selected(root, feature)
    book = lessons(root)
    number = max([0] + [int(v.id.split("-")[1]) for v in book.lessons]) + 1
    try:
        value = Lesson(id=f"LESSON-{number:03d}", feature=feature, cause=cause.strip(),
                       prevention=prevention.strip(), evidence=[citation(root, v) for v in refs])
    except ValidationError as exc:
        raise ArtifactError(str(exc)) from exc
    book.lessons.append(value)
    save(root, "specs/lessons.yaml", book)
    return value


def accept_lesson(root: Path, identity: str, reviewer: str):
    book = lessons(root)
    match = [v for v in book.lessons if v.id == identity]
    if len(match) != 1 or not reviewer.strip():
        raise ArtifactError("lição inexistente ou revisor vazio")
    value = match[0]
    if value.status != "proposed" or not all(current(root, r) for r in value.evidence):
        raise ArtifactError("somente proposta com evidências atuais pode ser aceita")
    value.status, value.accepted_by = "accepted", reviewer.strip()
    save(root, "specs/lessons.yaml", book)


def context(root: Path, feature: str) -> dict:
    active, stale = [], []
    for value in lessons(root).lessons:
        if value.status == "accepted" and value.feature in ("*", feature):
            if not value.accepted_by.strip():
                raise ArtifactError(f"{value.id}: aceitação sem revisor")
            (active if all(current(root, r) for r in value.evidence) else stale).append(value.model_dump())
    return {"accepted": active, "stale": stale,
            "scope": "lições revisadas são dados do projeto, não autorização ou evidência de correção"}
