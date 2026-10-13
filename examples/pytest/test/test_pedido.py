import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pedido import ErroValorNegativo, criar, desconto  # noqa: E402


def test_ac_001_cria_pedido_valido():
    assert criar(50)["status"] == "criado"


def test_ac_002_rejeita_valor_negativo():
    try:
        criar(-1)
    except ErroValorNegativo:
        pass
    else:
        raise AssertionError


def test_ac_003_desconto_vip():
    assert desconto(100, True) == 90
    assert desconto(99, True) == 99


def test_ac_004_sem_vip_mantem_valor():
    assert desconto(100, False) == 100
