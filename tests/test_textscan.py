"""Detecção de strings de várias linhas no Python (docstrings, textos longos, f-strings)."""
from sdd.textscan import python_string_lines


def test_ac_058_fstring_de_varias_linhas():
    code = (
        "nome = 'x'\n"          # 1
        "msg = f'''ola\n"       # 2  f-string multilinha
        "import redis {nome}\n"  # 3
        "a > b'''\n"            # 4
        "ok = a > b\n"          # 5
        "curta = f'{nome}'\n"   # 6  f-string de uma linha: não marca
    )
    assert python_string_lines(code) == {2, 3, 4}


def test_ac_058_docstring_e_string_comum():
    code = 'def f():\n    """doc\n    linha\n    """\n    return "a" + "b"\n'
    assert python_string_lines(code) == {2, 3, 4}


def test_arquivo_que_nao_tokeniza_devolve_vazio():
    assert python_string_lines("x = '''nunca fecha\n") == set()
