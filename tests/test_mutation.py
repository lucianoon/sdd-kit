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


def test_ac_093_temporarios_dos_filhos_nao_apagam_copias_irmas(tmp_path, monkeypatch):
    import tempfile
    from sdd import core, mutation

    root = tmp_path / "project"
    root.mkdir()
    project(root, FORTE)
    temp_area = tmp_path / "temporarios"
    temp_area.mkdir()
    sibling = temp_area / "sdd-mutate-irma"
    sibling.mkdir()
    marker = sibling / "preservar"
    marker.write_text("sentinela", encoding="utf-8")
    monkeypatch.setattr(tempfile, "tempdir", str(temp_area))
    for key in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(key, str(temp_area))
    (root / "limpar.py").write_text(encoding="utf-8", data=(
        "import pathlib, shutil, subprocess, sys, tempfile\n"
        "for p in pathlib.Path(tempfile.gettempdir()).glob('sdd-mutate-*'):\n"
        "    shutil.rmtree(p)\n"
        "sys.exit(subprocess.call([sys.executable, '-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider', 't']))\n"))
    proj = core.load(root)
    proj.config.mutation.command = f"{PY} limpar.py"
    rep = mutation.run_feature(proj, next(iter(proj.specs.values())))
    assert rep.ok and rep.score == 1, rep.error
    assert marker.read_text(encoding="utf-8") == "sentinela"


def test_ac_093_copia_apagada_nao_aprova_com_pontuacao_parcial(tmp_path):
    import json

    project(tmp_path, FORTE, min_score=0)
    (tmp_path / "apagar.py").write_text(encoding="utf-8", data=(
        "from pathlib import Path\nimport shutil\n"
        f"if Path('src/calc.py').read_text(encoding='utf-8') != {CODE!r}:\n"
        "    shutil.rmtree('src')\n"
        "    raise SystemExit(1)\n"))
    cfg_file = tmp_path / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg["mutation"]["command"] = f"{PY} apagar.py"
    cfg_file.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    r = mutate(tmp_path)
    assert r.exit_code == 2 and "execução de mutação incompleta" in r.stderr
    report = json.loads((tmp_path / ".sdd/mutation.json").read_text(encoding="utf-8"))
    assert report[0]["ok"] is False and report[0]["error"]
    assert any(m["status"] == "pending" for m in report[0]["mutants"])


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
    assert ops == {(3, "n→n+1"), (4, ">=→<")}  # x += 1 só gera a troca da constante


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


def test_ac_033_fim_de_string_escape_e_bloco_de_comentario(tmp_path):
    (tmp_path / "a.py").write_text(encoding="utf-8", data=(
        'msg = "a" + b  # c > d\n'      # string fecha antes do + ; comentário depois
        's = "x \\" > y"\n'             # aspas escapadas: o > continua dentro da string
    ))
    found = [(m.line, m.col, m.operator) for m in candidates(tmp_path, ["a.py"])]
    assert found == [(1, 11, "+→-")]
    (tmp_path / "b.ts").write_text(encoding="utf-8", data="/**\n * se a > b\n */\nconst ok = a > b;\n")
    assert [(m.line, m.col) for m in candidates(tmp_path, ["b.ts"])] == [(4, 14)]


def test_ac_088_orfaos_de_execucoes_mortas_sao_removidos(tmp_path, monkeypatch):
    # pastas sdd-mutate-* velhas de execuções mortas à força: limpas ao iniciar o mutate
    import os
    import time
    import tempfile as tf

    from sdd.mutation import sweep_stale

    monkeypatch.setattr(tf, "gettempdir", lambda: str(tmp_path))
    velha = tmp_path / "sdd-mutate-velha"
    (velha.mkdir(),)
    os.utime(velha, (time.time() - 25 * 3600,) * 2)  # 25 horas atrás
    recente = tmp_path / "sdd-mutate-recente"        # de uma execução concorrente
    recente.mkdir()
    assert sweep_stale() >= 1
    assert velha.exists() is False and recente.exists() is True


def test_ac_088_arvores_de_outros_sistemas_nao_sao_tocadas(tmp_path, monkeypatch):
    import tempfile as tf

    from sdd.mutation import sweep_stale

    monkeypatch.setattr(tf, "gettempdir", lambda: str(tmp_path))
    (tmp_path / "sdd-mutate-alien").mkdir()
    (tmp_path / "arquivo-cru").write_text(encoding="utf-8", data="x")
    (tmp_path / "outro-DA-ferramenta").mkdir()
    # só o prefixo próprio é candidato; max_age gigante não remove nada
    sweep_stale(max_age=10**9)
    assert (tmp_path / "sdd-mutate-alien").exists()
    sweep_stale(max_age=0)
    assert (tmp_path / "sdd-mutate-alien").exists() is False


def test_ac_088_rmtree_do_sweep_ignora_erros(tmp_path, monkeypatch):
    import shutil as sh
    import tempfile as tf

    from sdd import mutation

    vistos = []

    def espião(path, ignore_errors=False, **kw):
        vistos.append(ignore_errors)
        if not ignore_errors:
            raise PermissionError(path)  # mutant True→False morre aqui

    monkeypatch.setattr(sh, "rmtree", espião)
    monkeypatch.setattr(tf, "gettempdir", lambda: str(tmp_path))
    (tmp_path / "sdd-mutate-velha").mkdir()
    assert mutation.sweep_stale(max_age=0) == 1
    assert vistos == [True]  # sem ignore_errors, um diretório travado derrubaria o mutate


def test_ac_088_copias_mal_nascidas_nao_deixam_lixo(tmp_path, monkeypatch):
    import shutil as sh

    from sdd.mutation import _copy_project

    # copytree que falha a meio (legítimo: disco cheio) NÃO pode deixar a pasta para trás
    monkeypatch.setattr(sh, "copytree",
                        lambda src, dst, **kw: (_ for _ in ()).throw(OSError("disco cheio")))
    vistos = []
    real_rmtree = sh.rmtree

    def espião(path, ignore_errors=False, **kw):
        vistos.append(ignore_errors)
        return real_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(sh, "rmtree", espião)
    try:
        _copy_project(tmp_path, [])
    except OSError:
        pass
    else:
        raise AssertionError("falha de copytree deveria propagar")
    left = list(tmp_path.glob("sdd-mutate-*"))
    assert left == [], left
    assert vistos == [True]  # a limpeza da pasta mal nascida roda e tolera erros


def test_copia_isolada_ignora_git_e_referencia_dependencias(tmp_path):
    from sdd.mutation import _copy_project
    root = tmp_path / "proj"
    for d in (".git", ".sdd", "node_modules/lib", "pkg.egg-info", "src"):
        (root / d).mkdir(parents=True)
    (root / "src/a.py").write_text(encoding="utf-8", data="x = 1\n")
    (root / "node_modules/lib/index.js").write_text(encoding="utf-8", data="")
    if sys.platform != "win32":
        (root / "src/link.py").symlink_to("a.py")
    dest = _copy_project(root, ["node_modules"])
    try:
        names = {p.name for p in dest.iterdir()}
        assert names >= {"src", "node_modules"} and not names & {".git", ".sdd", "pkg.egg-info"}
        assert (dest / "node_modules").is_symlink()
        if sys.platform != "win32":
            assert (dest / "src/link.py").is_symlink()
    finally:
        import shutil
        shutil.rmtree(dest.parent, ignore_errors=True)


def test_pasta_com_nome_de_codigo_nao_quebra(tmp_path):
    project(tmp_path, FORTE)
    (tmp_path / "src/pasta.py").mkdir()
    (tmp_path / "src/LEIAME.md").write_text(encoding="utf-8", data="a > b\n")
    r = mutate(tmp_path)
    assert r.exit_code == 0, r.output
    assert "LEIAME" not in r.output


def test_ac_033_cerquilha_dentro_de_string_nao_vira_comentario(tmp_path):
    (tmp_path / "a.py").write_text(encoding="utf-8", data='url = "/doc#secao" + sufixo  # a > b\n')
    assert [(m.line, m.col, m.operator) for m in candidates(tmp_path, ["a.py"])] == [(1, 20, "+→-")]


def _ops(root: Path, name: str, code: str, only: tuple[str, ...] = ()) -> list[tuple[int, str]]:
    (root / name).write_text(encoding="utf-8", data=code)
    return [(m.line, m.operator) for m in candidates(root, [name]) if not only or m.operator in only]


COMPARA = ("<→>=", ">→<=", "and→or", "&&→||")


def test_ac_115_divisao_inteira_em_python_nao_vira_comentario(tmp_path):
    code = "def f(a, b):\n    return a // b > 0 and a < b  # x > y\n"
    assert _ops(tmp_path, "a.py", code, COMPARA) == [(2, "<→>="), (2, ">→<="), (2, "and→or")]
    assert all(m.mutated.endswith("# x > y") for m in candidates(tmp_path, ["a.py"]))


def test_ac_115_cerquilha_em_js_e_campo_privado_e_barras_em_c_sao_comentario(tmp_path):
    js = "class C { #n = 0; ok() { return this.#n > 1 && a; } }  // x > y\n"
    assert _ops(tmp_path, "a.js", js, COMPARA) == [(1, ">→<="), (1, "&&→||")]
    assert _ops(tmp_path, "a.c", "int x = a > b; // c > d\n", COMPARA) == [(1, ">→<=")]
    assert _ops(tmp_path, "b.py", "x = a > b  # c > d // e\n", COMPARA) == [(1, ">→<=")]


def test_ac_116_generics_nao_sao_mutados_e_comparacao_na_mesma_linha_e(tmp_path):
    ts = "const m: Map<string, Array<number>> = new Map(); if (a < b) {}\n"
    assert _ops(tmp_path, "a.ts", ts, COMPARA) == [(1, "<→>=")]
    java = "List<Integer> xs = f(a > b);\n"
    assert _ops(tmp_path, "A.java", java, COMPARA) == [(1, ">→<=")]
    rs = "let v: Vec<u8> = Vec::<u8>::new(); if a > b {}\n"
    assert _ops(tmp_path, "a.rs", rs, COMPARA) == [(1, ">→<=")]
    laco = "for (int i = 0; i<n; i++) { ok = x>y; }\n"  # comparação sem espaço continua sendo comparação
    assert _ops(tmp_path, "a.cpp", laco, COMPARA) == [(1, "<→>="), (1, ">→<=")]


def test_ac_116_tags_jsx_nao_sao_mutadas(tmp_path):
    jsx = 'const el = <div className="x">{a > b}</div>;\n'
    assert _ops(tmp_path, "a.jsx", jsx, COMPARA) == [(1, ">→<=")]
    assert _ops(tmp_path, "b.tsx", "const v = <Item k={1} />; ok = i<n;\n", COMPARA) == [(1, "<→>=")]


def test_ac_117_python_com_erro_de_sintaxe_e_descartado(tmp_path):
    code = "total = sum(x\n            for x\n            in xs)\nok = a in xs\n"
    found = _ops(tmp_path, "a.py", code, ("in→not in",))
    assert found == [(4, "in→not in")]  # a linha 3 viraria "not in xs)": SyntaxError, descartado


def test_ac_117_falha_do_build_e_mutante_invalido_fora_do_score(tmp_path):
    import json

    project(tmp_path, FORTE)
    cfg_file = tmp_path / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    # "Compilador" que rejeita <= : o mutante > → <= de maior() não compila.
    cfg["mutation"]["build"] = (f'"{PY}" -c "import sys; '
                                "sys.exit(1 if '<=' in open('src/calc.py').read() else 0)\"")
    cfg_file.write_text(encoding="utf-8", data=yaml.safe_dump(cfg))
    r = mutate(tmp_path)
    assert r.exit_code == 0, r.output
    assert "invalid   src/calc.py:2" in r.output, r.output
    rep = json.loads((tmp_path / ".sdd/mutation.json").read_text(encoding="utf-8"))[0]
    status = [m["status"] for m in rep["mutants"]]
    assert status.count("invalid") == 1 and "survived" not in status
    assert rep["score"] == 1.0  # o inválido não entra no denominador nem conta como morto
    md = (tmp_path / ".sdd/mutation.md").read_text(encoding="utf-8")
    assert "1 inválido(s)" in md and "src/calc.py:2" in md


def test_ac_117_build_que_falha_sem_mutacao_e_erro(tmp_path):
    project(tmp_path, FORTE)
    cfg_file = tmp_path / "specs/sdd.yaml"
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    cfg["mutation"]["build"] = f'"{PY}" -c "import sys; sys.exit(3)"'
    cfg_file.write_text(encoding="utf-8", data=yaml.safe_dump(cfg))
    r = mutate(tmp_path)
    assert r.exit_code == 2 and "build não passa sem mutações" in r.output, r.output


def test_ac_118_operadores_de_python(tmp_path):
    code = (
        "def f(a, b, xs):\n"
        "    if not a and b is None and a in xs:\n"
        "        return a * 2 / b % 3\n"
        "    for x in xs:\n"
        "        pass\n"
        "    return [x ** 2 for x in xs]\n"
    )
    found = _ops(tmp_path, "a.py", code)
    for esperado in [(2, "not→∅"), (2, "is→is not"), (2, "in→not in"), (3, "*→/"), (3, "/→*"),
                     (3, "%→*"), (3, "n→n+1"), (3, "return→nulo"), (6, "return→nulo"), (6, "n→n+1")]:
        assert esperado in found, (esperado, found)
    assert not [f for f in found if f[0] in (4, 6) and f[1] in ("in→not in", "*→/")], found
    mut = [(m.operator, m.mutated.strip()) for m in candidates(tmp_path, ["a.py"]) if m.line == 3]
    assert ("return→nulo", "return None") in mut
    assert [t for op, t in mut if op == "n→n+1"] == ["return a * 3 / b % 3", "return a * 2 / b % 4"]
    neg = "ok = a is not b and c not in d\n"
    assert _ops(tmp_path, "b.py", neg, ("is not→is", "not in→in", "not→∅", "is→is not", "in→not in")) == [
        (1, "is not→is"), (1, "not in→in")]


def test_ac_118_operadores_de_sintaxe_c(tmp_path):
    go = "if !ok { x := *p * 2 }\n"
    assert _ops(tmp_path, "a.go", go, ("!→∅", "*→/")) == [(1, "*→/"), (1, "!→∅")]  # *p é ponteiro
    assert _ops(tmp_path, "a.rs", 'println!("x"); let ok = a != b;\n', ("!→∅",)) == []
    js = "function f(a, b) {\n  return a + b;\n}\nfunction g() {\n  return (\n    1\n  );\n}\n"
    (tmp_path / "a.js").write_text(encoding="utf-8", data=js)
    rets = [(m.line, m.mutated.strip()) for m in candidates(tmp_path, ["a.js"]) if m.operator == "return→nulo"]
    assert rets == [(2, "return undefined;")]  # o return de várias linhas não é mutado


def test_ac_119_mais_e_menos_grudados_em_identificador_e_notacao_cientifica(tmp_path):
    code = "x = size+1\ny = 1e-5\nz = n-1\nw = 2.5E+3\n"
    assert _ops(tmp_path, "a.py", code, ("+→-", "-→+")) == [(1, "+→-"), (3, "-→+")]


def test_ac_118_operadores_de_python_nao_valem_para_ruby(tmp_path):
    so_python = ("not→∅", "is→is not", "is not→is", "in→not in", "not in→in")
    assert _ops(tmp_path, "a.rb", "ok = a in xs and not b\nfor x in xs do end\n", so_python) == []


def test_ac_118_return_com_aspas_escapadas_e_de_uma_linha(tmp_path):
    code = 'def f(b):\n    return "a\\"(" + b\n'  # o ( está dentro da string: a linha é completa
    assert _ops(tmp_path, "a.py", code, ("return→nulo",)) == [(2, "return→nulo")]


def test_ac_116_generic_com_espaco_interno_nao_e_mutado(tmp_path):
    ts = "const xs: Array< number > = f(a > b);\n"
    assert _ops(tmp_path, "a.ts", ts, COMPARA) == [(1, ">→<=")]
