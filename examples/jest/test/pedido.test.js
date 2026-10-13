const { criar, desconto } = require("../src/pedido");

describe("Pedido", () => {
  it("AC-001 cria pedido válido", () => {
    expect(criar(50).status).toBe("criado");
  });
  it("AC-002 rejeita valor negativo", () => {
    expect(() => criar(-1)).toThrow();
  });
});

// ID no describe: cobre todos os testes do bloco
describe("AC-003 desconto VIP", () => {
  it("aplica 10% a partir de 100", () => expect(desconto(100, true)).toBe(90));
  it("não aplica abaixo de 100", () => expect(desconto(99, true)).toBe(99));
});

test.each([[100, false, 100], [200, false, 200]])("AC-004 sem VIP mantém %i", (v, vip, esperado) => {
  expect(desconto(v, vip)).toBe(esperado);
});
