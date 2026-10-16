"""Regras de arquitetura (ARCH-NNN) e modos de falha das dependências."""
import copy
import sys
from pathlib import Path

import yaml
import pytest
from typer.testing import CliRunner

from sdd import arch, core
from sdd.cli import app

runner = CliRunner()
PY = sys.executable

RULES = {"rules": [{
    "id": "ARCH-001", "description": "domínio não depende de infra",
    "from": ["src/domain/**"],
    "forbid": ["openai", "langchain*", "@langchain/*", "redis"],
    "forbid_paths": ["src/infra/**"],
}]}


def project(root: Path, files: dict[str, str], rules: dict | None = None):
    (root / "specs/features/FEATURE-001").mkdir(parents=True)
    (root / "specs/sdd.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(
        {"tests": {"command": f"{PY} -c \"pass\"", "junit": ".sdd/j.xml"}}))
    (root / "specs/features/FEATURE-001/spec.yaml").write_text(encoding="utf-8", data=yaml.safe_dump({
        "feature": "f", "version": 1, "size": "small",
        "requirements": [{"id": "REQ-001", "description": "d",
                          "acceptance": [{"id": "AC-001", "given": "g", "when": "w", "then": "t"}]}]}))
    (root / "specs/architecture.yaml").write_text(encoding="utf-8", data=yaml.safe_dump(rules or RULES))
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(encoding="utf-8", data=content)
    return root


def arch_report(root: Path) -> dict:
    proj = core.load(root)
    assert proj.errors == [], proj.errors
    return arch.check(proj)


def where(rep) -> set[tuple[str, int, str]]:
    return {(v["file"], v["line"], v["import"]) for v in rep["violations"]}


# --- REQ-012: regras de arquitetura ----------------------------------------------

def test_ac_043_import_de_modulo_proibido_reprova(tmp_path):
    project(tmp_path, {
        "src/domain/pedido.py": "from dataclasses import dataclass\nimport openai\nfrom langchain_core.messages import X\n",
        "src/infra/llm.py": "import openai\n",  # fora da regra: permitido
    })
    rep = arch_report(tmp_path)
    assert where(rep) == {("src/domain/pedido.py", 2, "openai"),
                          ("src/domain/pedido.py", 3, "langchain_core.messages")}
    assert not rep["ok"]


def test_ac_043_check_reprova_e_relata(tmp_path):
    project(tmp_path, {"src/domain/a.py": "import redis\n"})
    r = runner.invoke(app, ["check", "-C", str(tmp_path)])
    assert r.exit_code == 1
    assert "ARCH-001: src/domain/a.py:1 importa 'redis'" in r.stderr
    md = (tmp_path / ".sdd/report.md").read_text(encoding="utf-8")
    assert "## Arquitetura" in md and "`src/domain/a.py:1`" in md


def test_ac_043_modulo_parecido_nao_e_falso_positivo(tmp_path):
    project(tmp_path, {"src/domain/a.py": "import openai_helpers_local\nimport redistribute\n"})
    assert arch_report(tmp_path)["violations"] == []


def test_ac_044_import_relativo_que_alcanca_infra_reprova(tmp_path):
    project(tmp_path, {
        "src/domain/pedidos/servico.py": "from ...infra.db import Sessao\nfrom ..valores import Moeda\n",
        "src/domain/regras.ts": "import { db } from '../infra/db';\nimport { x } from './valores';\n",
    })
    rep = arch_report(tmp_path)
    assert where(rep) == {("src/domain/pedidos/servico.py", 1, "...infra.db"),
                          ("src/domain/regras.ts", 1, "../infra/db")}


def test_ac_045_js_ts_e_go(tmp_path):
    project(tmp_path, {
        "src/domain/a.ts": (
            "import { ChatOpenAI } from '@langchain/openai';\n"
            "const r = require('redis');\n"
            "const m = await import('openai');\n"
            "import {\n  Foo,\n} from '@langchain/core';\n"
            "import './efeito';\n"
        ),
        "src/domain/b.go": (
            'package domain\n'
            'import "github.com/redis/go-redis"\n'
            'import (\n  "fmt"\n  oa "openai"\n)\n'
        ),
    }, rules={"rules": [{**RULES["rules"][0], "forbid": RULES["rules"][0]["forbid"] + ["github.com/redis/*"]}]})
    rep = arch_report(tmp_path)
    assert where(rep) == {
        ("src/domain/a.ts", 1, "@langchain/openai"), ("src/domain/a.ts", 2, "redis"),
        ("src/domain/a.ts", 3, "openai"), ("src/domain/a.ts", 6, "@langchain/core"),
        ("src/domain/b.go", 2, "github.com/redis/go-redis"), ("src/domain/b.go", 5, "openai"),
    }


def test_ac_046_excecao_com_motivo_vira_registro(tmp_path):
    project(tmp_path, {"src/domain/a.py": "import openai  # sdd: allow ARCH-001 adapter legado até AD-007\n"})
    rep = arch_report(tmp_path)
    assert rep["ok"] and rep["violations"] == []
    assert rep["exceptions"][0]["reason"] == "adapter legado até AD-007"


def test_ac_046_excecao_sem_motivo_nao_vale(tmp_path):
    project(tmp_path, {"src/domain/a.py": "import openai  # sdd: allow ARCH-001\n"})
    rep = arch_report(tmp_path)
    assert rep["violations"][0]["detail"] == "marcação sdd: allow sem motivo não vale"


def test_ac_046_excecao_de_outra_regra_nao_vale(tmp_path):
    project(tmp_path, {"src/domain/a.py": "import openai  # sdd: allow ARCH-999 outro motivo\n"})
    assert len(arch_report(tmp_path)["violations"]) == 1


def test_ac_047_regra_que_nao_casa_nada_reprova(tmp_path):
    project(tmp_path, {"src/core/a.py": "import openai\n"})  # não existe src/domain
    rep = arch_report(tmp_path)
    assert not rep["ok"]
    assert "nenhum arquivo casa" in rep["problems"][0]


def test_ac_048_comentarios_e_docstrings_nao_contam(tmp_path):
    project(tmp_path, {
        "src/domain/a.py": '"""\nimport openai\n"""\n# import redis\nx = 1\n',
        "src/domain/b.ts": "// import x from 'openai';\n/* import 'redis' */\n",
    })
    assert arch_report(tmp_path)["violations"] == []


def test_cli_arch(tmp_path):
    project(tmp_path, {"src/domain/a.py": "import openai\n"})
    r = runner.invoke(app, ["arch", "-C", str(tmp_path)])
    assert r.exit_code == 1 and "ARCH-001  src/domain/a.py:1  importa 'openai'" in r.stderr
    (tmp_path / "src/domain/a.py").write_text(encoding="utf-8", data="from .modelo import Pedido\n")
    r = runner.invoke(app, ["arch", "-C", str(tmp_path)])
    assert r.exit_code == 0 and "APROVADO" in r.output


def test_regra_sem_proibicao_e_invalida(tmp_path):
    project(tmp_path, {}, rules={"rules": [{"id": "ARCH-001", "description": "d", "from": ["src/**"]}]})
    assert any("forbid" in e for e in core.load(tmp_path).errors)


def test_regra_duplicada_e_invalida(tmp_path):
    project(tmp_path, {}, rules={"rules": [RULES["rules"][0], RULES["rules"][0]]})
    assert any("ARCH-001 duplicada" in e for e in core.load(tmp_path).errors)


# --- REQ-013: modos de falha -------------------------------------------------------

DEP = {"name": "gateway de pagamento", "kind": "external_api", "timeout_ms": 5000,
       "retry": {"max_attempts": 3}, "fallback": "enfileira para reprocessar",
       "side_effects": True, "idempotent": True, "covered_by": ["AC-001"]}


def spec_with_deps(root: Path, deps) -> str:
    from test_design import BASE_SPEC, project as design_project
    s = copy.deepcopy(BASE_SPEC)
    if deps is None:
        s["design"].pop("dependencies")
    else:
        s["design"]["dependencies"] = deps
    design_project(root, s)
    return "\n".join(core.load(root).errors)


def dep(**over) -> dict:
    d = copy.deepcopy(DEP)
    d.update(over)
    return d


def test_ac_049_dependencia_completa_e_valida(tmp_path):
    assert spec_with_deps(tmp_path, [dep()]) == ""


def test_ac_049_campos_de_falha_obrigatorios(tmp_path):
    d = dep()
    for k in ("timeout_ms", "retry", "fallback"):
        d.pop(k)
    e = spec_with_deps(tmp_path, [d])
    assert "timeout_ms" in e and "retry" in e and "fallback" in e


def test_ac_050_retry_em_efeito_colateral_nao_idempotente(tmp_path):
    e = spec_with_deps(tmp_path, [dep(idempotent=False)])
    assert "pode duplicar a transação" in e


def test_ac_050_sem_retry_nao_precisa_de_idempotencia(tmp_path):
    d = dep(idempotent=False, retry={"max_attempts": 1}, reconciliation="conciliação diária com o extrato")
    assert spec_with_deps(tmp_path, [d]) == ""


def test_ac_070_escrita_sem_idempotencia_nem_status_exige_reconciliacao(tmp_path):
    e = spec_with_deps(tmp_path, [dep(idempotent=False, retry={"max_attempts": 1})])
    assert "declare `reconciliation`" in e


def test_ac_070_consulta_de_status_permite_retry_sem_idempotencia(tmp_path):
    d = dep(idempotent=False, status_query=True, retry={"max_attempts": 3})
    assert spec_with_deps(tmp_path, [d]) == ""


def test_ac_070_leitura_nao_exige_reconciliacao(tmp_path):
    d = dep(side_effects=False, idempotent=False, retry={"max_attempts": 3})
    assert spec_with_deps(tmp_path, [d]) == ""


def test_ac_051_covered_by_inexistente(tmp_path):
    e = spec_with_deps(tmp_path, [dep(covered_by=["AC-404"])])
    assert "covered_by 'AC-404' não é AC, NFR nem EVAL desta spec" in e


def test_ac_052_dependencies_precisa_ser_declarado(tmp_path):
    assert "dependencies" in spec_with_deps(tmp_path, None)


def test_ac_052_lista_vazia_e_afirmacao_valida(tmp_path):
    assert spec_with_deps(tmp_path, []) == ""


def test_ac_053_suite_que_excede_timeout_reprova(tmp_path):
    from test_sdd import make
    make(tmp_path, "def test_ac_001(): pass\n")
    cfg_file = tmp_path / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg["tests"].update(command=f"{PY} -c \"import time; time.sleep(5)\"", timeout=1)
    cfg_file.write_text(encoding="utf-8", data=yaml.safe_dump(cfg))
    report = core.check(core.load(tmp_path))
    assert not report["ok"]
    assert "suíte de testes excedeu o timeout de 1s" in report["problems"]


def test_relatorio_mostra_dependencias(tmp_path):
    spec_with_deps(tmp_path, [dep()])
    md = core.render_markdown({"ok": True, "problems": [], "gates": [], "risks": [],
                               "criteria": [{"feature": "p", "origin": "REQ-001", "id": "AC-001",
                                             "text": "t", "verdict": "OK", "tests": []}],
                               "dependencies": core.dependency_matrix(core.load(tmp_path))})
    assert "| gateway de pagamento (external_api) | 5000 ms | 3 | sim | sim |" in md
    assert "AC-001 (OK)" in md


def test_ac_058_aspas_triplas_em_string_nao_escondem_imports(tmp_path):
    project(tmp_path, {"src/domain/a.py": (
        "SEP = '\"\"\"'\n"           # aspas triplas dentro de uma string comum
        "import openai\n"
        'DOC = """texto\nimport redis\n"""\n'  # import dentro de string longa: não conta
    )})
    assert where(arch_report(tmp_path)) == {("src/domain/a.py", 2, "openai")}


def test_ac_044_import_esm_com_extensao_e_pacote_inteiro(tmp_path):
    project(tmp_path, {
        "src/domain/a.ts": "import { db } from '../infra/db.js';\n",   # ESM exige extensão
        "src/domain/b.py": "from ..infra import Sessao\n",            # pacote inteiro
    })
    assert where(arch_report(tmp_path)) == {("src/domain/a.ts", 1, "../infra/db.js"),
                                            ("src/domain/b.py", 1, "..infra")}


def test_ac_043_subcaminho_de_pacote_conta(tmp_path):
    project(tmp_path, {"src/domain/a.ts": "import { Chat } from 'openai/resources/chat';\n"})
    assert where(arch_report(tmp_path)) == {("src/domain/a.ts", 1, "openai/resources/chat")}


def test_ac_045_go_string_fora_do_import_nao_conta(tmp_path):
    project(tmp_path, {"src/domain/a.go": (
        'package domain\n'
        'func Provedor() string {\n'
        '    return "openai"\n'
        '}\n'
        'import (\n    "fmt"\n)\n'
        'func Outro() string {\n    return "redis"\n}\n'
    )})
    assert arch_report(tmp_path)["violations"] == []


def test_ac_048_dependencias_embutidas_e_nao_codigo_sao_ignorados(tmp_path):
    project(tmp_path, {
        "src/domain/a.py": "x = 1\n",
        "src/domain/node_modules/lib/index.js": "require('openai');\n",
        "src/domain/LEIAME.md": "import openai\n",
    })
    (tmp_path / "src/domain/pasta.py").mkdir()  # diretório com nome de arquivo de código
    rep = arch_report(tmp_path)
    assert rep["violations"] == [] and rep["files"] == 1


def test_sem_regras_aprova(tmp_path):
    project(tmp_path, {"src/a.py": "import openai\n"}, rules={"rules": []})
    rep = arch_report(tmp_path)
    assert rep["ok"] is True and rep["rules"] == []


@pytest.mark.parametrize("statement", [
    "from .. import infra\n", "from ..infra import (\n    db,\n)\n",
    "import infra.db\n", "from infra import db\n",
])
def test_ac_108_ast_imports_pacote_modulo_e_absolutos(tmp_path, statement):
    project(tmp_path, {"src/domain/a.py": statement, "src/infra/db.py": "x = 1\n", "src/infra/__init__.py": ""})
    rep = arch_report(tmp_path)
    assert not rep["ok"] and any(v["file"] == "src/domain/a.py" for v in rep["violations"])


@pytest.mark.parametrize("content", [b"from openai import (", b"\xff\x80"])
def test_ac_109_arquivo_impossivel_de_analisar_reprova(tmp_path, content):
    project(tmp_path, {"src/domain/a.py": "x = 1\n"})
    (tmp_path / "src/domain/a.py").write_bytes(content)
    rep = arch_report(tmp_path)
    assert not rep["ok"] and "não foi possível analisar" in rep["problems"][0]


def test_ac_110_constituicao_mantem_resultado_por_regra(tmp_path):
    project(tmp_path, {"src/domain/a.py": "import openai\n", "src/infra/db.py": "x = 1\n"}, rules={"rules": [
        RULES["rules"][0], {"id": "ARCH-002", "description": "infra sem redis", "from": ["src/infra/**"], "forbid": ["redis"]}]})
    (tmp_path / "specs/constitution.yaml").write_text(yaml.safe_dump({"principles": [
        {"id": "CONST-01", "rule": "domínio", "enforced_by": ["ARCH-001"]},
        {"id": "CONST-02", "rule": "infra", "enforced_by": ["ARCH-002"]}]}), encoding="utf-8")
    result = runner.invoke(app, ["arch", "-C", str(tmp_path)])
    assert result.exit_code == 1
    import json
    report = json.loads((tmp_path / ".sdd/arch.json").read_text(encoding="utf-8"))
    assert report["rule_results"] == {"ARCH-001": "FALHOU", "ARCH-002": "OK"}
    assert [c["status"] for c in report["constitution"]] == ["VIOLADO", "APROVADO"]


@pytest.mark.parametrize("statement", ["from infra import db\n", "from ..infra import db\n"])
def test_ac_108_proibicao_do_submodulo_com_pacote_permitido(tmp_path, statement):
    project(tmp_path, {"src/domain/a.py": statement, "src/infra/__init__.py": "", "src/infra/db.py": "x = 1\n"},
            rules={"rules": [{"id": "ARCH-001", "description": "domínio sem banco",
                              "from": ["src/domain/**"], "forbid_paths": ["src/infra/db"]}]})
    rep = arch_report(tmp_path)
    assert not rep["ok"] and len(rep["violations"]) == 1
    assert rep["violations"][0]["matched"] == "src/infra/db"
