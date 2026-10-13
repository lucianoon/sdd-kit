"""Esqueleto de spec: IDs livres no projeto e as seções que o `size` exige.

Determinístico, sem LLM. Os campos a preencher levam o marcador PREENCHER, e qualquer
linha com ele reprova o `sdd validate` apontando a linha: o esqueleto não passa por spec
pronta. Quem preenche (pessoa ou agente) troca cada marcador por conteúdo real.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .core import CONFIG_PATH, PLACEHOLDER

ID_ANY = re.compile(r"\b(REQ|AC|NFR|EVAL)-(\d{3,})\b")
NAME_OK = re.compile(r"^[a-z0-9][a-z0-9-]*$")
P = PLACEHOLDER


class SpecifyError(ValueError):
    pass


def _existing(root: Path) -> tuple[dict[str, int], set[str], int]:
    """Maior número por prefixo, features existentes e maior FEATURE-NNN. Lê texto bruto
    para funcionar mesmo quando alguma spec ainda não valida."""
    top = {"REQ": 0, "AC": 0, "NFR": 0, "EVAL": 0}
    features: set[str] = set()
    last_dir = 0
    for f in sorted((root / "specs/features").glob("*/spec.yaml")):
        text = f.read_text(encoding="utf-8")
        for kind, num in ID_ANY.findall(text):
            top[kind] = max(top[kind], int(num))
        m = re.search(r"^feature:\s*([\w-]+)", text, re.MULTILINE)
        if m:
            features.add(m.group(1))
        d = re.match(r"FEATURE-(\d+)$", f.parent.name)
        if d:
            last_dir = max(last_dir, int(d.group(1)))
    return top, features, last_dir


def _design_required(root: Path, size: str) -> bool:
    cfg_file = root / CONFIG_PATH
    cfg = {}
    if cfg_file.exists():
        try:
            cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            cfg = {}
    return bool(cfg.get("require_design")) and size in cfg.get("design_required_for", ["large", "complex"])


def render(name: str, size: str, acs: int, ids: dict[str, int], with_design: bool) -> str:
    def nid(kind: str, offset: int = 1) -> str:
        return f"{kind}-{ids[kind] + offset:03d}"

    ac_lines = "\n".join(
        f"      - id: {nid('AC', i)}\n"
        f"        given: \"{P}: estado inicial\"\n"
        f"        when: \"{P}: ação\"\n"
        f"        then: \"{P}: resultado observável e testável\""
        for i in range(1, acs + 1))
    out = f"""\
feature: {name}
version: 1
size: {size}
summary: "{P}: o problema que esta feature resolve, em uma frase"
out_of_scope:
  - "{P}: o que explicitamente NÃO será feito (ou remova a lista)"
assumptions: []
open_questions: []
decisions: []

requirements:
  - id: {nid('REQ')}
    description: "{P}: comportamento esperado"
    acceptance:
{ac_lines}
"""
    if with_design:
        nfr = nid("NFR")
        out += f"""
design:
  numbers:
    - id: {nfr}
      metric: "{P}: ex. latency_p95"
      max: 0                      # {P}: limite real
      unit: "{P}: ms, req/s, %..."
      at: "{P}: condição de carga"
      source: "{P}: de onde veio o número (medição, contrato, PO)"
  data_flow:
    ingress:
      - via: "{P}: http | stream | arquivo | fila"
        frequency: "{P}: volume e frequência"
    egress:
      - to: "{P}: onde os dados são consumidos"
  alternatives:
    - name: "{P}: alternativa escolhida"
      chosen: true
      why: "{P}: por que esta"
    - name: "{P}: alternativa descartada"
      why_not: "{P}: por que não"
  risks:
    - area: performance           # {P}: performance | security | availability | data_integrity | cost | compliance | other
      severity: medium            # {P}: low | medium | high
      description: "{P}: o risco"
      mitigated_by: [{nfr}]
  dependencies: []                # {P}: liste as dependências externas (timeout, retry, fallback...) ou confirme que não há
"""
    out += f"""
invariants: []
quality_gates: []
paths:
  - "{P}: glob do código desta feature, ex. src/{name}/**"
"""
    return out


def create(root: Path, name: str, size: str = "medium", acs: int = 1) -> tuple[Path, dict[str, str]]:
    if not NAME_OK.match(name):
        raise SpecifyError(f"nome inválido '{name}': use minúsculas, dígitos e hífen (ex.: criar-pedido)")
    if size not in ("small", "medium", "large", "complex"):
        raise SpecifyError(f"size inválido '{size}': small | medium | large | complex")
    if acs < 1:
        raise SpecifyError("--acs precisa ser pelo menos 1")
    ids, features, last_dir = _existing(root)
    if name in features:
        raise SpecifyError(f"já existe uma feature '{name}'")
    folder = root / "specs/features" / f"FEATURE-{last_dir + 1:03d}"
    folder.mkdir(parents=True)
    with_design = _design_required(root, size)
    path = folder / "spec.yaml"
    path.write_text(render(name, size, acs, ids, with_design), encoding="utf-8")
    allocated = {"REQ": f"REQ-{ids['REQ'] + 1:03d}",
                 "AC": ", ".join(f"AC-{ids['AC'] + i:03d}" for i in range(1, acs + 1))}
    if with_design:
        allocated["NFR"] = f"NFR-{ids['NFR'] + 1:03d}"
    return path, allocated
