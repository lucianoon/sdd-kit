import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from fretes import frete  # noqa: E402


def test_ac_201_vip_acima_do_limite_nao_paga():
    assert frete(120, True, 2.0) == 0.0


def test_ac_202_vip_abaixo_do_limite_paga_a_tabela():
    assert frete(90, True, 2.0) == 15.0


def test_ac_203_sem_vip_paga_a_tabela():
    assert frete(500, False, 2.0) == 15.0


def test_ac_204_peso_excedente_e_cobrado_por_kg():
    assert frete(90, True, 7.0) == 21.0
