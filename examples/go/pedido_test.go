package pedidos

import "testing"

// Convenção 1: ID no nome da função, com underscore (Go não aceita hífen).
func TestAC_001_CriaPedidoValido(t *testing.T) {
	if s, _ := Criar(50); s != "criado" {
		t.Fatal(s)
	}
}

// Convenção 2: ID colado, estilo CamelCase.
func TestAC002RejeitaValorNegativo(t *testing.T) {
	if _, err := Criar(-1); err == nil {
		t.Fatal("esperava erro")
	}
}

// Convenção 3: subtestes com t.Run (idiomático em Go, table-driven).
func TestDesconto(t *testing.T) {
	t.Run("AC-003 VIP com 100 ou mais", func(t *testing.T) {
		if Desconto(100, true) != 90 {
			t.Fatal()
		}
	})
	t.Run("AC-004 sem VIP", func(t *testing.T) {
		if Desconto(200, false) != 200 {
			t.Fatal()
		}
	})
}
