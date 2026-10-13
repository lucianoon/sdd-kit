LIMITE_VIP = 100


class ErroValorNegativo(ValueError):
    pass


def criar(valor: int) -> dict:
    if valor < 0:
        raise ErroValorNegativo("valor negativo")
    return {"valor": valor, "status": "criado"}


def desconto(valor: int, vip: bool) -> float:
    return valor * 0.9 if vip and valor >= LIMITE_VIP else valor
