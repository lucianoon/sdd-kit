from pedidos import LIMITE_VIP

TABELA = 15.0  # frete base
POR_KG_EXCEDENTE = 3.0
LIMITE_PESO = 5.0


def frete(valor: int, vip: bool, peso: float) -> float:
    if vip and valor >= LIMITE_VIP:
        return 0.0  # mesmo limite do desconto VIP, garantido por LIMITE_VIP
    total = TABELA + max(0.0, peso - LIMITE_PESO) * POR_KG_EXCEDENTE
    return total
