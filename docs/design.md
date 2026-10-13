# Desenho arquitetural

A seção `design` das specs `large`/`complex`: números, fluxo de dados, alternativas, riscos, dependências e modos de falha.

## Desenho arquitetural: seção `design`

Antes de implementar, specs `large`/`complex` registram o desenho. Com `require_design: true`
em `specs/sdd.yaml` (`sdd enable design` ou preset `padrao`), elas não passam no
`sdd validate` sem ele.

```yaml
design:
  numbers:                       # números são um divisor de águas
    - id: NFR-001                # com id: requisito não funcional VERIFICÁVEL
      metric: latency_p95
      max: 200
      unit: ms
      at: 50 req/s de pico
      source: estimativa do PO   # obrigatório: de onde veio o número
    - {metric: payload, max: 64, unit: KB, source: contrato}
  data_flow:                     # como os dados chegam e onde são consumidos
    ingress: [{via: http, source: app mobile, frequency: 50 req/s de pico}]
    egress:  [{to: postgres, consumers: [dashboard], freshness: até 5 min}]
  alternatives:                  # peça alternativas
    - {name: síncrono + postgres, chosen: true, why: volume baixo}
    - {name: fila + worker, why_not: complexidade sem ganho no volume atual}
  risks:                         # olhe para onde está o risco
    - area: performance          # performance | security | availability | data_integrity | cost | compliance | other
      severity: medium           # low | medium | high
      description: pico de fim de mês dobra o tráfego
      mitigated_by: [NFR-001]    # AC ou NFR desta spec...
    - {area: cost, severity: low, description: ..., accepted: motivo}   # ...ou aceite explícito
```

O que o `sdd validate` exige:

| Regra | Por quê |
|---|---|
| Ao menos 1 número, com limite (`max`/`min`), unidade e `source` | sem números, a IA chuta e entrega algo genérico; `source` impede número inventado |
| Fluxo com ao menos uma entrada e uma saída | obriga a decidir HTTP vs stream vs arquivo, analítico vs memória |
| Ao menos 2 alternativas, **exatamente 1** escolhida, todas justificadas | evita ir direto para a primeira solução |
| Todo risco com `mitigated_by` (IDs existentes na spec) ou `accepted` | risco sem tratamento é risco ignorado |

E o `sdd check` trata cada `NFR-NNN` como um critério de aceitação: precisa de um teste ou
benchmark com o ID no nome (`test_nfr_001_p95_abaixo_de_200ms`) passando. O relatório
ganha uma matriz de riscos que mostra o estado de cada mitigação (`NFR-001 (OK)`).

O `AGENTS.md` gerado instrui o agente a seguir essa ordem: números perguntados ao humano,
fluxo de dados, alternativas, riscos, e aprovação do `design` antes de escrever código.

## Modos de falha: `design.dependencies`

Toda dependência externa declara como o sistema se comporta quando ela falha:

```yaml
design:
  dependencies:
    - name: gateway de pagamento
      kind: external_api        # llm | vector_store | database | cache | queue | external_api | tool | process
      timeout_ms: 5000
      retry: {max_attempts: 3, backoff: exponential}
      fallback: enfileira para reprocessar e avisa o cliente
      side_effects: true        # cobra, escreve, envia, cria pedido
      idempotent: true          # chave de idempotência: repetir não cobra duas vezes
      covered_by: [AC-012, AC-013]   # testes que simulam timeout, 429, indisponibilidade
```

O `sdd validate` exige:

| Regra | Pergunta de arquitetura que responde |
|---|---|
| `timeout_ms`, `retry` e `fallback` em toda dependência | Como tratar timeout, rate limit e indisponibilidade do provedor? |
| `max_attempts > 1` com `side_effects: true` exige `idempotent: true` | Como impedir que o agente execute a mesma transação duas vezes? |
| `covered_by` com IDs que existem na spec | O tratamento de falha é testado ou só prometido? |
| `dependencies` declarado (lista vazia é uma afirmação explícita) | Alguém pensou nas dependências? |

O relatório do `check` traz a tabela de dependências com o estado dos testes de cada uma.
