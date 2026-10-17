"""Explicit proposal/apply/archive lifecycle with baseline conflict detection."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from . import core
from .artifacts import ArtifactError, atomic_write, confined
from .learning import digest, read_model, save, selected, slug
from .models import Strict, Spec


class Change(Strict):
    version: Literal[1] = 1
    name: str
    feature: str
    target: str
    baseline_sha256: str
    status: Literal["draft", "applied", "archived"] = "draft"
    applied_sha256: str = ""
    reason: str


def paths(name: str):
    base = f"specs/changes/{slug(name)}"
    return base + "/change.yaml", base + "/spec.yaml", base + "/baseline.yaml"


def propose(root: Path, name: str, feature: str, reason: str):
    if not reason.strip():
        raise ArtifactError("informe o motivo da mudança")
    target, _ = selected(root, feature)
    manifest, proposal, baseline = paths(name)
    for value in (manifest, proposal, baseline):
        if confined(root, value).exists():
            raise ArtifactError(f"mudança existente preservada: {name}")
    source = confined(root, target)
    text = source.read_text(encoding="utf-8")
    change = Change(name=name, feature=feature, target=target, baseline_sha256=digest(source), reason=reason)
    atomic_write(root, baseline, text)
    atomic_write(root, proposal, text)
    save(root, manifest, change)
    return change.model_dump()


def inspect(root: Path, name: str):
    manifest, proposal, baseline = paths(name)
    change = read_model(root, manifest, Change)
    if change.name != name:
        raise ArtifactError("nome do manifesto diverge do diretório")
    before = read_model(root, baseline, Spec)
    after = read_model(root, proposal, Spec)
    if digest(confined(root, baseline)) != change.baseline_sha256:
        raise ArtifactError("baseline da proposta foi alterada")
    if before.feature != change.feature or after.feature != change.feature:
        raise ArtifactError("mudança não pode renomear a feature")
    target, _ = selected(root, change.feature)
    if target != change.target:
        raise ArtifactError("destino divergente da feature")
    def entries(spec):
        out = {r.id: r.model_dump() for r in spec.requirements}
        out.update({cid: {"origin": origin, "text": text} for cid, origin, text in spec.criteria()})
        return out
    left, right = entries(before), entries(after)
    delta = {"added": sorted(right.keys() - left.keys()), "removed": sorted(left.keys() - right.keys()),
             "modified": sorted(k for k in left.keys() & right.keys() if left[k] != right[k])}
    return change, after, delta


def apply(root: Path, name: str):
    change, proposed, delta = inspect(root, name)
    if change.status != "draft" or digest(confined(root, change.target)) != change.baseline_sha256:
        raise ArtifactError("mudança já aplicada ou spec vigente alterada; reconcilie a proposta")
    manifest, proposal, _ = paths(name)
    # Publish only a candidate accepted by the full loader; restore on failure.
    baseline = confined(root, change.target).read_text(encoding="utf-8")
    atomic_write(root, change.target, confined(root, proposal).read_text(encoding="utf-8"))
    try:
        errors = core.load(root).errors
        if errors:
            raise ArtifactError("proposta inválida: " + "; ".join(errors))
        change.status = "applied"
        change.applied_sha256 = digest(confined(root, change.target))
        save(root, manifest, change)
    except Exception:
        atomic_write(root, change.target, baseline)
        raise
    return {"status": change.status, "delta": delta, "verification": "NÃO_EXECUTADA"}


def archive(root: Path, name: str):
    change, _, delta = inspect(root, name)
    manifest, proposal, _ = paths(name)
    target = confined(root, change.target)
    if (change.status != "applied" or digest(target) != change.applied_sha256
            or digest(confined(root, proposal)) != change.applied_sha256):
        raise ArtifactError("somente proposta aplicada e inalterada pode ser arquivada")
    before = digest(target)
    report = core.check(core.load(root))
    if not report["ok"]:
        raise ArtifactError("check atual reprovou: " + "; ".join(report["problems"]))
    if digest(target) != before:
        raise ArtifactError("spec alterada durante a verificação")
    # Full fresh check is stored with its scope; mutation/evals are never implied.
    import json
    atomic_write(root, f"specs/changes/{name}/verification.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    change.status = "archived"
    save(root, manifest, change)
    return {"status": "archived", "delta": delta, "verification": "check",
            "scope": "check executado nesta chamada; diff, mutate e eval não executados"}
