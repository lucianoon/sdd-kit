function criar(valor) {
  if (valor < 0) throw new Error("valor negativo");
  return { valor, status: "criado" };
}
function desconto(valor, vip) {
  return vip && valor >= 100 ? valor * 0.9 : valor;
}
module.exports = { criar, desconto };
