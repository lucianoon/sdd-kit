package pedidos

import "errors"

func Criar(valor float64) (string, error) {
	if valor < 0 {
		return "", errors.New("valor negativo")
	}
	return "criado", nil
}

func Desconto(valor float64, vip bool) float64 {
	if vip && valor >= 100 {
		return valor * 0.9
	}
	return valor
}
