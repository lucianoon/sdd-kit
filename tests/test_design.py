import copy
import sys
import time
from pathlib import Path

import yaml

from sdd import core

PY = sys.executable

BASE_SPEC = {
    "feature": "pedidos",
    "version": 1,
    "requirements": [{
        "id": "REQ-001", "description": "d",
        "acceptance": [{"id": "AC-001", "given": "g", "when": "w", "then": "t"}],
    }],
    "design": {
        "numbers": [{"id": "NFR-001", "metric": "latency_p95", "max": 200, "unit": "ms",
                     "source": "PO"}],
        "data_flow": {
            "ingress": [{"via": "http", "frequency": "50 req/s"}],
            "egress": [{"to": "postgres"}],
        },
        "alternatives": [
            {"name": "síncrono", "chosen": True, "why": "simples"},
            {"name": "fila", "why_not": "complexo demais"},
        ],
        "risks": [{"area": "performance", "severity": "high", "description": "pico",
                   "mitigated_by": ["NFR-001"]}],
        "dependencies": [],
    },
}


def project(root: Path, spec: dict | None = None, require_design=True, tests: str = ""):
    (root / "specs/features/FEATURE-001").mkdir(parents=True)
    cfg = {"version": 1, "require_design": require_design,
           "tests": {"command": f"{PY} -m pytest -q -p no:cacheprovider --junitxml=.sdd/junit.xml t",
                     "junit": ".sdd/junit.xml"}}
    (root / "specs/sdd.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(cfg))
    (root / "specs/features/FEATURE-001/spec.yaml").write_text(encoding="utf-8", data=
        yaml.safe_dump(spec if spec is not None else BASE_SPEC, allow_unicode=True))
    (root / "t").mkdir()
    (root / "t/test_x.py").write_text(encoding="utf-8", data=tests)
    return root


def spec_with(mutate) -> dict:
    s = copy.deepcopy(BASE_SPEC)
    mutate(s)
    return s


def errors(root: Path) -> str:
    return "\n".join(core.load(root).errors)


def test_design_completo_e_valido(tmp_path):
    assert errors(project(tmp_path)) == ""


def test_ac_016_design_obrigatorio(tmp_path):
    project(tmp_path, spec_with(lambda s: s.pop("design")))
    assert "seção `design` obrigatória" in errors(tmp_path)


def test_ac_016_design_opcional_quando_desligado(tmp_path):
    project(tmp_path, spec_with(lambda s: s.pop("design")), require_design=False)
    assert errors(tmp_path) == ""


def test_ac_017_menos_de_duas_alternativas(tmp_path):
    project(tmp_path, spec_with(lambda s: s["design"]["alternatives"].pop()))
    assert "alternatives" in errors(tmp_path)


def test_ac_017_nenhuma_ou_duas_escolhidas(tmp_path):
    def duas(s):
        s["design"]["alternatives"][1].update(chosen=True, why="x")
    project(tmp_path, spec_with(duas))
    assert "exatamente uma alternativa" in errors(tmp_path)


def test_ac_017_descartada_sem_justificativa(tmp_path):
    project(tmp_path, spec_with(lambda s: s["design"]["alternatives"][1].pop("why_not")))
    assert "why_not" in errors(tmp_path)


def test_ac_018_risco_sem_tratamento(tmp_path):
    project(tmp_path, spec_with(lambda s: s["design"]["risks"][0].pop("mitigated_by")))
    assert "mitigated_by" in errors(tmp_path)


def test_ac_018_mitigacao_com_id_inexistente(tmp_path):
    project(tmp_path, spec_with(lambda s: s["design"]["risks"][0].update(mitigated_by=["AC-777"])))
    assert "'AC-777' não é AC, NFR ou EVAL desta spec nem regra ARCH" in errors(tmp_path)


def test_ac_018_risco_aceito_com_motivo_e_valido(tmp_path):
    def aceito(s):
        s["design"]["risks"][0] = {"area": "cost", "severity": "low", "description": "d",
                                   "accepted": "custo irrelevante no volume atual"}
    assert errors(project(tmp_path, spec_with(aceito))) == ""


def test_ac_019_numero_sem_limite(tmp_path):
    project(tmp_path, spec_with(lambda s: s["design"]["numbers"][0].pop("max")))
    assert "max e/ou min" in errors(tmp_path)


def test_ac_019_numero_sem_unidade_ou_fonte(tmp_path):
    project(tmp_path, spec_with(lambda s: [s["design"]["numbers"][0].pop(k) for k in ("unit", "source")]))
    e = errors(tmp_path)
    assert "unit" in e and "source" in e


def test_ac_020_nfr_sem_teste_reprova(tmp_path):
    project(tmp_path, tests="def test_ac_001_x(): pass\n")
    report = core.check(core.load(tmp_path))
    nfr = next(r for r in report["criteria"] if r["id"] == "NFR-001")
    assert nfr["verdict"] == "SEM_TESTE"
    assert not report["ok"]


def test_ac_020_nfr_com_teste_aprova(tmp_path):
    project(tmp_path, tests="def test_ac_001_x(): pass\ndef test_nfr_001_p95(): pass\n")
    report = core.check(core.load(tmp_path))
    assert report["ok"], report["problems"]
    assert "latency_p95 <= 200 ms" in core.render_markdown(report)
    assert "NFR-001 (OK)" in core.render_markdown(report)  # risco aponta o estado da mitigação


def test_ac_021_junit_antigo_nao_e_reaproveitado(tmp_path):
    project(tmp_path, spec_with(lambda s: s.pop("design")), require_design=False)
    (tmp_path / ".sdd").mkdir()
    (tmp_path / ".sdd/junit.xml").write_text(encoding="utf-8", data=
        '<testsuite><testcase classname="t" name="test_ac_001_x"/></testsuite>')
    cfg_file = tmp_path / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg["tests"]["command"] = f'{PY} -c "pass"'  # roda, mas não gera JUnit
    cfg_file.write_text(encoding="utf-8", data=yaml.safe_dump(cfg))
    report = core.check(core.load(tmp_path))
    assert not report["ok"]
    assert any("não gerou" in p for p in report["problems"])


def test_nfr_001_validate_200_specs_em_menos_de_2s(tmp_path):
    project(tmp_path)
    for i in range(2, 201):
        s = copy.deepcopy(BASE_SPEC)
        s["feature"] = f"f{i}"
        s["requirements"][0]["id"] = f"REQ-{i:04d}"
        s["requirements"][0]["acceptance"][0]["id"] = f"AC-{i:04d}"
        s["design"]["numbers"][0]["id"] = f"NFR-{i:04d}"
        s["design"]["risks"][0]["mitigated_by"] = [f"NFR-{i:04d}"]
        d = tmp_path / f"specs/features/FEATURE-{i:03d}"
        d.mkdir()
        (d / "spec.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(s, allow_unicode=True))
    start = time.perf_counter()
    proj = core.load(tmp_path)
    elapsed = time.perf_counter() - start
    assert proj.errors == [] and len(proj.specs) == 200
    assert elapsed < 2, f"{elapsed:.2f}s"
