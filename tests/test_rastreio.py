"""Reconhecimento de IDs nos nomes de teste das principais stacks."""
import pytest

from sdd.core import ID_IN_TEST


def ids(name: str) -> set[str]:
    return {f"{(m['a'] or m['b']).upper()}-{m['n']}" for m in ID_IN_TEST.finditer(name)}


@pytest.mark.parametrize("name,esperado", [
    ("test_ac_001_pedido_persistido", {"AC-001"}),            # pytest
    ("test_nfr_001_p95", {"NFR-001"}),
    ("Pedido AC-001 cria pedido válido", {"AC-001"}),          # jest-junit
    ("Pedido &gt; AC-002 rejeita", {"AC-002"}),                # vitest
    ("AC-003 desconto VIP aplica 10%", {"AC-003"}),            # ID no describe
    ("TestAC_001_CriaPedidoValido", {"AC-001"}),               # Go com underscore
    ("TestAC002RejeitaValorNegativo", {"AC-002"}),             # Go CamelCase
    ("TestDesconto/AC-003_VIP_com_100", {"AC-003"}),           # Go subteste t.Run
    ("testAC004MantemValor", {"AC-004"}),                      # JUnit camelCase
    ("shouldPersist_AC_005", {"AC-005"}),                      # JUnit sufixo
    ("AC001_CriaPedido", {"AC-001"}),                          # xUnit/C#
    ("test_ac_001_e_ac_002_juntos", {"AC-001", "AC-002"}),     # vários IDs
])
def test_ac_060_convencoes_das_stacks(name, esperado):
    assert ids(name) == esperado


@pytest.mark.parametrize("name", [
    "test_mac_001_endereco", "MAC-001", "HVAC100_sensor", "track_001", "TRACK_001",
    "test_place_123", "ac_01_curto_demais", "spac100",
])
def test_ac_060_sem_falso_positivo(name):
    assert ids(name) == set()
