"""sdd mutate: sensor de discriminação determinístico."""
import hashlib
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from sdd.cli import app
from sdd.mutation import candidates

runner = CliRunner()
PY = sys.executable

CODE = '''\
def maior(a, b):
    return a > b


def desconto(total, vip):
    if vip and total >= 100:
        return total - 10
    return total
'''
FORTE = '''\
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from calc import maior, desconto

def test_maior():
    assert maior(2, 1) is True
    assert maior(1, 2) is False
    assert maior(1, 1) is False

def test_desconto():
    assert desconto(100, True) == 90
    assert desconto(99, True) == 99
    assert desconto(100, False) == 100
'''
FRACO = '''\
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from calc import maior, desconto

def test_roda():
    maior(2, 1)
    desconto(100, True)
'''


def project(root: Path, tests: str, code: str = CODE, min_score: float = 0.8):
    (root / "specs/features/FEATURE-001").mkdir(parents=True)
    (root / "specs/sdd.yaml").write_text(encoding="utf-8", data=yaml.safe_dump({
        "tests": {"command": f"{PY} -m pytest -q -x -p no:cacheprovider t", "junit": ".sdd/j.xml"},
        "mutation": {"min_score": min_score, "timeout": 60},
    }))
    (root / "specs/features/FEATURE-001/spec.yaml").write_text(encoding="utf-8", data=yaml.safe_dump({
        "feature": "calc", "version": 1, "size": "small", "paths": ["src/**"],
        "requirements": [{"id": "REQ-001", "description": "d",
                          "acceptance": [{"id": "AC-001", "given": "g", "when": "w", "then": "t"}]}],
    }))
    (root / "src").mkdir()
    (root / "src/calc.py").write_text(encoding="utf-8", data=code)
    (root / "t").mkdir()
    (root / "t/test_calc.py").write_text(encoding="utf-8", data=tests)
    return root


def mutate(root: Path):
    return runner.invoke(app, ["mutate", "-C", str(root)])


def test_ac_029_testes_fortes_matam_todos_e_aprovam(tmp_path):
    r = mutate(project(tmp_path, FORTE))
    assert r.exit_code == 0, r.output
    assert "survived" not in r.output
    assert "score 100%" in r.output


def test_ac_030_testes_fracos_reprovam_com_arquivo_e_linha(tmp_path):
    r = mutate(project(tmp_path, FRACO))
    assert r.exit_code == 1, r.output
    assert "survived  src/calc.py:2" in r.output
    report = (tmp_path / ".sdd/mutation.md").read_text(encoding="utf-8")
    assert "REPROVADO" in report and "`src/calc.py:2`" in report


def test_ac_031_arvore_de_trabalho_intacta(tmp_path):
    project(tmp_path, FRACO)
    before = hashlib.sha256((tmp_path / "src/calc.py").read_bytes()).hexdigest()
    mutate(tmp_path)
    after = hashlib.sha256((tmp_path / "src/calc.py").read_bytes()).hexdigest()
    assert before == after
    assert sorted(p.name for p in tmp_path.iterdir()) == [".sdd", "specs", "src", "t"]


def test_ac_032_suite_quebrada_sem_mutacao_e_erro(tmp_path):
    r = mutate(project(tmp_path, FORTE.replace("is True", "is False", 1)))
    assert r.exit_code == 2
    assert "não passa sem mutações" in r.output


def test_ac_033_strings_comentarios_e_marcacao_nao_sao_mutados(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text(encoding="utf-8", data=
        'msg = "a > b and c"  # x > y\n'
        "# return a > b\n"
        "limite = a > b  # sdd: no-mutate\n"
        "ok = a > b\n"
    )
    found = candidates(tmp_path, ["src/a.py"])
    assert [(m.line, m.operator) for m in found] == [(4, ">→<=")]


def test_operadores_nao_quebram_setas_e_incrementos(tmp_path):
    (tmp_path / "a.ts").write_text(encoding="utf-8", data="const f = (x) => x->y;\ni++;\nx += 1;\nif (a >= b) {}\n")
    ops = {(m.line, m.operator) for m in candidates(tmp_path, ["a.ts"])}
    assert ops == {(4, ">=→<")}


LOOP = '''\
def contar(n):
    i = 0
    while i != n:
        i = i + 1
    return i
'''
LOOP_TEST = '''\
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from calc import contar

def test_contar():
    assert contar(3) == 3
'''


def test_ac_056_mutante_que_trava_conta_como_morto(tmp_path):
    project(tmp_path, LOOP_TEST, code=LOOP)
    cfg_file = tmp_path / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg["mutation"]["timeout"] = 3
    cfg_file.write_text(encoding="utf-8", data=yaml.safe_dump(cfg))
    r = mutate(tmp_path)
    assert "timeout   src/calc.py:4" in r.output, r.output
    assert r.exit_code == 0


def test_ac_057_mutacao_de_mesmo_tamanho_e_detectada(tmp_path):
    # "a + b" -> "a - b" não muda o tamanho do arquivo: cache de bytecode mascararia o mutante.
    soma = "def soma(a, b):\n    return a + b\n"
    teste = FORTE.split("from calc")[0] + "from calc import soma\n\ndef test_soma():\n    assert soma(2, 3) == 5\n"
    project(tmp_path, teste, code=soma)
    r = mutate(tmp_path)
    assert "killed    src/calc.py:2" in r.output, r.output
    assert r.exit_code == 0


def test_ac_057_testes_rodam_sem_escrever_bytecode(tmp_path):
    # Determinístico: a suíte só passa se o mutate desligar o cache de bytecode.
    project(tmp_path, FORTE)
    cfg_file = tmp_path / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg["tests"]["command"] = (f"{PY} -c \"import os, sys; "
                               "sys.exit(0 if os.environ.get('PYTHONDONTWRITEBYTECODE') == '1' else 1)\"")
    cfg_file.write_text(encoding="utf-8", data=yaml.safe_dump(cfg))
    r = mutate(tmp_path)
    assert "não passa sem mutações" not in r.output, r.output


def test_ac_057_cada_escrita_tem_mtime_maior_e_preserva_quebras(tmp_path):
    from sdd.mutation import _Clock, _read, _write
    f = tmp_path / "a.py"
    clock = _Clock()
    _write(f, "x = 1\r\ny = 2\r\n", clock)
    t1 = f.stat().st_mtime
    _write(f, "x = 1\r\ny = 3\r\n", clock)  # mesmo tamanho, escrita imediata
    assert f.stat().st_mtime >= t1 + 2
    assert _read(f) == "x = 1\r\ny = 3\r\n"


def test_ac_058_aspas_triplas_em_string_nao_escondem_codigo(tmp_path):
    (tmp_path / "a.py").write_text(encoding="utf-8", data=(
        "SEP = '\"\"\"'\n"
        "ok = a > b\n"
        'DOC = """\nx > y\n"""\n'
    ))
    assert [(m.line, m.operator) for m in candidates(tmp_path, ["a.py"])] == [(2, ">→<=")]
