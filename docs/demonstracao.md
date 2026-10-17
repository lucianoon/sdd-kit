# Demonstração: detectar um bug e verificar a correção

Use uma cópia temporária do exemplo pytest para não alterar seu checkout:

```bash
python scripts/demo.py
```

Requer sdd-kit instalado no mesmo Python e pytest. O script copia `examples/pytest`,
executa check, introduz um bug real no cálculo de desconto, confirma a reprovação,
restaura o código e confirma a aprovação. Se a falha passar despercebida ou a correção
não passar, o script sai com erro. A cópia temporária é removida ao final.

A spec exige 10% de desconto para cliente VIP a partir de 100. Ao trocar o multiplicador
por 0.8, o teste AC-003 observa o valor errado: o vínculo nominal é acompanhado de uma
asserção concreta. A demonstração cobre esse comportamento; não prova adequação de
todos os testes do projeto.

Depois, veja como o mesmo fluxo pode ser guiado por agente, com revisão e lições:

```bash
sdd integrate codex
sdd guide criar-pedido --stage plan --json
sdd adequacy template criar-pedido
sdd cite tests/test_pedido.py:18
```

Os últimos comandos pressupõem sua própria feature e teste. Preencha a revisão com um
revisor separado e siga [o guia dos complementos](complementos.md).
