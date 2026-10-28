# Especificação

Como escrever specs que o `sdd` consegue verificar: requisitos, critérios, rastreio pelo nome do teste, tamanho, premissas, tarefas e critério vago.

## Começando uma feature

```bash
$ sdd specify criar-pedido --size large --acs 2
criado   specs/features/FEATURE-002/spec.yaml
IDs      REQ: REQ-002  AC: AC-002, AC-003  NFR: NFR-002
```

O esqueleto já traz as seções que o `size` exige (design só em `large`/`complex`) e IDs que
não colidem com nenhuma outra spec. Cada campo a preencher leva o marcador `PREENCHER`, e
o `sdd validate` reprova apontando arquivo e linha até que todos virem conteúdo real.

## Como funciona

**1. Spec** — `specs/features/<FEATURE>/spec.yaml`:

```yaml
feature: create-order
version: 1
requirements:
  - id: REQ-001
    description: Criar pedido válido
    acceptance:
      - id: AC-001
        given: Pedido válido
        when: API recebe solicitação
        then: Pedido é persistido
quality_gates: [type_check]
```

**2. Convenção de rastreio** — o nome do teste contém o ID do critério:

```python
def test_ac_001_pedido_persistido(): ...
```

```ts
it("AC-001 persiste o pedido", ...)
```

```go
func TestAC_001_PersistePedido(t *testing.T) { ... }   // ou TestAC001..., ou t.Run("AC-001 ...")
```

Convenções reconhecidas, verificadas no CI com os runners reais (pasta `examples/`):

| Stack | Exemplos de nome | JUnit gerado por |
|---|---|---|
| pytest | `test_ac_001_x`, `test_nfr_001_p95` | `--junitxml` |
| jest / vitest | `it("AC-001 ...")`, `describe("AC-003 ...")` cobre o bloco, `test.each` | jest-junit / reporter `junit` |
| Go | `TestAC_001_X`, `TestAC001X`, subteste `t.Run("AC-003 ...")` | go-junit-report ou gotestsum |
| JUnit / xUnit | `testAC001`, `shouldPersist_AC_001`, `AC001_Cria` | nativo |

Um teste pode cobrir vários ACs; um AC pode ter vários testes. Palavras que só parecem IDs
(`MAC-001`, `HVAC100`, `track_001`) não contam.

**3. Config** — `specs/sdd.yaml` é o único lugar que conhece a stack:

```yaml
tests:
  command: "pytest -q --junitxml=.sdd/junit.xml"   # qualquer runner que gere JUnit XML
  junit: ".sdd/junit.xml"
gates:
  type_check: "mypy src"
```

**4. Veredito** — por critério de aceitação:

| Veredito | Significado | Aprova? |
|---|---|---|
| `OK` | ao menos um teste passou, nenhum falhou | sim |
| `SEM_TESTE` | nenhum teste cita o ID | não |
| `FALHOU` | algum teste do critério falhou | não |
| `PULADO` | todos os testes do critério foram pulados | não |

Também reprova: ID citado em teste que não existe em nenhuma spec, suíte com exit code ≠ 0,
gate com exit code ≠ 0, JUnit não gerado. O JUnit anterior é apagado antes de cada execução.

Relatório em `.sdd/report.md` e `.sdd/report.json`.

## Rigor proporcional: `size`

Uma correção de uma linha não precisa de análise de alternativas. Cada spec declara o tamanho:

| size | Quando | `design` exigido? |
|---|---|---|
| `small` | ≤3 arquivos, cabe numa frase | não |
| `medium` | feature clara, poucos passos | não |
| `large` | vários componentes | sim |
| `complex` | ambiguidade, domínio novo | sim |

Configurável em `design_required_for`. Duas travas contra subdimensionar: `size` ausente
conta como `large`, e o `sdd diff` reprova feature `small` que altera mais de
`small_max_files` (padrão 3) arquivos de código.

## Escopo fechado: premissas, perguntas e decisões

```yaml
assumptions:          # lacuna resolvida com um padrão escolhido; nada de suposição silenciosa
  - {assumption: moeda não especificada, chosen: BRL 2 casas, rationale: único mercado}
open_questions:       # pergunta sem answer BLOQUEIA o sdd validate
  - {question: pode editar após pago?, answer: não; vira cancelamento + novo pedido}
decisions: [AD-001]   # decisões de projeto que a feature segue
```

`specs/decisions.yaml` guarda as decisões que valem para todas as features (`AD-NNN`).
Decisão substituída fica no histórico com `status: superseded` e `superseded_by`; spec que
ainda referencia uma decisão substituída não valida.

### Requisitos implícitos: `dimensions`

Algumas dimensões quase sempre escondem decisões que ninguém pediu em voz alta. Ao criar a
spec, diga quais a feature toca:

```bash
sdd specify cobrar-pedido --touches pagamentos,concorrencia
```

| Dimensão | Perguntas que o catálogo acrescenta |
|---|---|
| `persistencia` | estado parcial em falha no meio; retenção e quem apaga |
| `autenticacao` | quem pode e o que recebe quem não pode; credencial expirando no meio |
| `pagamentos` | cobrança com resultado desconhecido; reembolso, estorno e parcial |
| `chamadas-externas` | serviço lento ou fora do ar; repetir duplica efeito? |
| `concorrencia` | duas operações sobre o mesmo registro; quem vence |
| `transicoes-de-estado` | transições permitidas e proibidas; repetir uma transição |

A spec ganha `dimensions` e as perguntas em `open_questions`, que bloqueiam o `validate` até
serem respondidas. Sem `--touches`, o carregamento procura termos de cada dimensão no
resumo, nos requisitos e nos critérios (sem acento e sem caixa, no início de uma palavra) e
**avisa** quando a spec cita uma dimensão que não declara. É heurística: o aviso nunca
bloqueia. Declare a dimensão depois de levantar as perguntas com o usuário.

### Aprovação humana: `approvals`

Com a camada `approval` (`require_approval: true`), a spec e o plano passam pelo usuário
antes de o agente implementar (AD-008). O registro guarda as palavras de quem aprovou e o
hash do conteúdo aprovado:

```bash
sdd approve criar-pedido --stage spec --by "Ana" --quote "pode seguir com essa spec"
sdd approve criar-pedido --stage plan --by "Ana" --quote "plano ok"
```

```yaml
approvals:
- stage: spec
  by: Ana
  date: 2026-10-28
  quote: pode seguir com essa spec
  digest: sha256:9f2c…
```

| Etapa | O hash cobre | Pré-condição |
|---|---|---|
| `spec` | tudo exceto `design`, `tasks` e `approvals` | sem pergunta aberta nem campo `PREENCHER` |
| `plan` | `design` e `tasks` (sem `status` e `evidence`) | spec aprovada e atual; spec sem erros |

O hash vem do documento validado, não do texto: comentário, formatação e o avanço de
`status`/`evidence` das tarefas não pedem nova aprovação. Mudou o conteúdo da etapa, ela fica
`DESATUALIZADO`. Aprovação ausente ou desatualizada é **aviso** no `validate` e bloqueia só
o `sdd guide --stage implement`; `check`, `diff` e `mutate` não a leem. O kit não autentica
quem aprovou: a revisão do PR confere o diff da spec.

## Tarefas: `tasks`

```yaml
tasks:
  - id: T-01
    title: Persistir agendamentos
    origin: [REQ-002]              # REQ/AC/NFR/EVAL desta spec, ARCH ou CONST
    done_when: migração aplica e registros persistem
    status: done
    evidence: [AC-004]
  - id: T-02
    title: Impedir reservas concorrentes
    origin: [AC-005]
    depends_on: [T-01]
    done_when: teste concorrente comprova uma única reserva
```

O `validate` reprova tarefa sem origem válida, dependência inexistente ou em ciclo (mostra
o caminho), tarefa `done` sem evidência e **requisito órfão**: AC, NFR ou EVAL que nenhuma
tarefa cita (citar o REQ cobre todos os seus ACs). O `check` reprova tarefa `done` cuja
evidência não passa. Com `require_tasks: true` (`sdd enable tasks` ou preset `padrao`), specs
`large`/`complex` precisam de tarefas.

## Critério vago

`then: "o agente responde corretamente"` não define resultado observável. O `validate`
avisa quando um critério usa termos como "rápido", "seguro", "corretamente", "adequado" ou
"fácil" (e equivalentes em inglês) sem nenhum valor numérico. Com `strict_criteria: true`,
vira erro. "Lista em até 300 ms com 10 mil registros" passa.
