# sdd-kit

SDD (Specification-Driven Development) agnóstico para desenvolvimento assistido por IA.

> LLMs propõem e implementam. Especificações definem os contratos.
> Ferramentas independentes verificam. Humanos governam as decisões de maior risco.

O agente (Claude Code, Codex, Cursor, Copilot...) escolhe **como** implementar.
Quem decide se está **correto** é o `sdd check`, que roda fora do LLM, na sua máquina e no CI.

## Instalação

```bash
pipx install git+https://github.com/lucianoon/sdd-kit
# desenvolvimento: git clone ... && pip install -e ".[dev]"
```

## Uso

```bash
sdd init        # cria specs/, AGENTS.md e .github/workflows/sdd.yml
sdd specify x   # esqueleto da spec: IDs livres no projeto, seções exigidas pelo --size
sdd validate    # schema, IDs, design, perguntas abertas, decisões
sdd check       # roda testes + gates; exit 1 se algum AC/NFR não tiver teste passando
sdd diff        # exit 1 se código de uma feature mudou sem a spec mudar junto
sdd mutate      # exit 1 se os testes não detectam código errado (score < mínimo)
sdd eval        # exit 1 se o comportamento do LLM não atinge os critérios estatísticos
sdd arch        # exit 1 se uma camada importa o que não pode (também roda no check)
sdd schema      # JSON Schema da spec (autocomplete no editor, outras ferramentas)
```

O fluxo que o `AGENTS.md` gerado ensina ao agente: **dimensionar → especificar → desenhar
→ quebrar em tarefas → implementar → verificar**, com profundidade proporcional ao `size`.
O `sdd` não confia que o agente seguiu o fluxo: cada etapa deixa um artefato que um comando
verifica.

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

## Desenho arquitetural: seção `design`

Antes de implementar, specs `large`/`complex` registram o desenho. Com `require_design: true`
em `specs/sdd.yaml` (padrão no `sdd init`), elas não passam no `sdd validate` sem ele.

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

## Divergência: `sdd diff`

O `check` garante que a spec atual está coberta. O `diff` garante que ela **continua sendo
a verdade** quando o código muda. Cada spec declara o código que é dela:

```yaml
# specs/features/FEATURE-001/spec.yaml
paths: ["src/pedidos/**"]
```

```yaml
# specs/sdd.yaml
code: ["src/**"]     # o que conta como código de produção
```

```bash
sdd diff --base origin/main
```

Compara com o merge-base da branch alvo, incluindo alterações não commitadas e arquivos
não rastreados.

| Situação | Resultado |
|---|---|
| Arquivo em `paths` de uma feature mudou e a pasta da spec não | **reprova** |
| Arquivo em `code` mudou e nenhuma feature o declara | **reprova** (código sem dono) |
| Código e spec da feature mudaram juntos | aprova |
| Só a spec mudou | aprova com aviso (spec-first é legítimo) |
| Arquivo fora de `code` (docs, CI...) | ignorado |

**Refatoração sem mudança de comportamento** não precisa mexer na spec. Declare no commit:

```
refactor: extrai validação de pedido

SDD-No-Spec-Change: só reorganização interna, sem mudança de comportamento
```

O diff aprova e imprime o motivo. A exceção fica auditável no histórico do git, e a revisão
humana decide se o motivo procede. Exit codes: `0` aprovado, `1` reprovado, `2` erro de git
(ex.: base inexistente; no CI, use `fetch-depth: 0`).

## Qualidade dos testes: `sdd mutate`

O `check` prova que existe um teste com o ID e que ele passa. Não prova que o teste
**verifica** algo: `def test_ac_001(): criar_pedido()` passa sem assert nenhum. O `mutate`
fecha essa brecha sem LLM:

1. Copia o projeto para um diretório temporário (o seu nunca é tocado).
2. Confere que a suíte passa sem mutações (senão, sai com código 2).
3. Para cada mutante, troca **um** operador no código dos `paths` da feature
   (`>`→`<=`, `==`→`!=`, `and`→`or`, `True`→`False`, `+`→`-`...) e roda os testes.
4. Testes falharam = mutante morto. Passaram = **sobreviveu**: aquele comportamento não é
   verificado por ninguém.

```
$ sdd mutate
== pedidos
  killed    src/pedidos/regras.py:12      >=→<
  survived  src/pedidos/regras.py:18      and→or
  score 50% (mínimo 80%)
REPROVADO — relatório em .sdd/mutation.md
```

```yaml
# specs/sdd.yaml
mutation:
  min_score: 0.8
  max_mutants: 50          # amostra determinística e espalhada: mesmo resultado em toda execução
  timeout: 120             # por mutante; estouro (ex.: loop infinito) conta como morto
  command: "pytest -q -x"  # padrão: tests.command. Falhar rápido acelera muito
  env:
    PYTHONPATH: "{root}/src"   # pacote instalado em modo editável apontaria para o original
```

- `--base origin/main` muta só os arquivos alterados no PR (é o que o workflow gerado faz).
- `--feature pedidos` limita a uma feature; `--max 20` sobrescreve a amostra.
- Linha com `sdd: no-mutate` é ignorada (para mutantes equivalentes, ex. log).
- Strings, comentários, docstrings e imports não são mutados.

**Custo:** cada mutante roda a suíte. Com uma suíte de 15 s, 50 mutantes levam até ~12 min.
Use um `command` mais rápido (subconjunto, `-x`) e `--base` no CI.

Para mutação mais profunda, ferramentas dedicadas (mutmut, Stryker, pitest, cargo-mutants)
entram como `gates` comuns; o `mutate` embutido existe para funcionar em qualquer stack sem
instalar nada.

## Arquitetura executável: `specs/architecture.yaml`

"Domínio não depende de infraestrutura" escrito num documento não impede ninguém, humano
ou agente, de dar `import openai` dentro da regra de negócio. Aqui a regra é verificada:

```yaml
rules:
  - id: ARCH-001
    description: Domínio não depende de infraestrutura nem de provedores de IA
    from: ["src/domain/**"]
    forbid: [openai, anthropic, "langchain*", "langgraph*", "@langchain/*", redis, sqlalchemy]
    forbid_paths: ["src/adapters/**", "src/infra/**"]   # alcançados por import relativo
```

```
$ sdd arch
ERRO  ARCH-001  src/domain/pedido.py:3  importa 'openai'
1 regra(s), 14 arquivo(s) — REPROVADO
```

- Lê imports de **Python** (`import`, `from`, relativos), **JS/TS** (`from`, `require`,
  `import()`, multilinha, ESM com extensão) e **Go** (simples e em bloco). Comentários e
  strings longas não contam (o Python é lido com o tokenizador da própria linguagem).
- `forbid` casa módulos e subcaminhos (`openai` pega `openai.types` e `openai/resources`,
  mas não `openai_helpers`); aceita curingas.
- Regra cujo `from` não casa nenhum arquivo **reprova**: glob errado não pode virar
  "aprovado em silêncio".
- Exceção pontual, auditável, na linha do import:
  `import openai  # sdd: allow ARCH-001 adapter legado até a AD-007`. Sem motivo não vale;
  as exceções aparecem no relatório.
- Riscos do `design` podem apontar para regras (`mitigated_by: [ARCH-001]`); o relatório
  mostra se a regra está `OK` ou `VIOLADA`.
- Roda dentro do `sdd check`. Para outras linguagens ou regras mais ricas (ciclos, camadas
  transitivas), use ArchUnit, dependency-cruiser ou import-linter como `gates`.

É o que torna verificável a pergunta "como trocar o provedor de LLM sem alterar a lógica de
negócio?": se o domínio não importa o provedor, trocar o adapter não toca no negócio.

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

## Sistemas com LLM: `sdd eval`

Testes cobrem o código ao redor do modelo. O comportamento do modelo (escolher a tool
certa, não alucinar, seguir o formato) varia entre execuções: um teste que passa uma vez
não prova nada. Para isso, a spec declara **evals**:

```yaml
evals:
  - id: EVAL-001
    metric: tool_selection_accuracy
    dataset: evals/datasets/tools.jsonl   # versionado no repo; cada linha com "id" único
    min_cases: 200                        # casos distintos exigidos em CADA execução
    runs: 3                               # execuções independentes
    threshold: {min: 0.9}                 # ou {max: 0.02} para taxas ruins (ex. alucinação)
    max_run_spread: 0.05                  # reprova se variar demais entre execuções
    use_lower_bound: true                 # compara o limite inferior do IC 95%, não a média
    judge: deterministic                  # ou llm (ver abaixo)
```

**O harness é seu**, em qualquer linguagem e com qualquer SDK. Ele só grava resultados
**brutos**, um por caso e execução, em `.sdd/evals/EVAL-001.jsonl`:

```json
{"case": "c17", "run": 1, "pass": true}
{"case": "c17", "run": 2, "pass": false}
```

(ou `"score": 0.82` com `aggregate: mean_score`). **O harness não declara a nota:** o
`sdd eval` calcula tudo e confere a integridade:

| Veredito | Quando |
|---|---|
| `OK` | dentro do limite e estável |
| `FORA_DO_LIMITE` | média (ou limite do IC 95%) fora de `threshold` |
| `INSTAVEL` | maior − menor valor entre execuções acima de `max_run_spread` |
| `INCOMPLETO` | menos execuções ou casos que o exigido, caso fora do dataset, caso duplicado |
| `SEM_RESULTADO` | harness não gravou o arquivo (resultados antigos são apagados antes) |

```
$ sdd eval
OK              EVAL-001  tool_selection_accuracy = 0.913
FORA_DO_LIMITE  EVAL-002  hallucination_rate = 0.041  (média 0.041 > máximo 0.02)
REPROVADO — relatório em .sdd/eval.md
```

Por que o **intervalo de confiança** importa: 87% de acerto em 30 casos parece passar num
mínimo de 85%, mas o IC 95% vai de ~79% a ~92%. Com `use_lower_bound: true` o sdd só aprova
quando até o cenário pessimista está acima do limite. Isso obriga datasets do tamanho certo.

**Travas contra afrouxar a régua:**
- `sdd validate` exige que o dataset exista, tenha IDs únicos e pelo menos `min_cases` casos.
- `sdd diff` reprova PR que altera o dataset de um eval sem alterar a spec.
- Coloque prompts e config do modelo nos `paths` da feature: trocar prompt sem atualizar a
  spec também reprova no `diff`.

**Juiz LLM.** Algumas qualidades só são medíveis por outro modelo ("a resposta é fiel ao
documento?"). O kit permite, de forma explícita e auditável (decisão AD-004):
`judge: llm` só é aceito com `evals.allow_llm_judge: true` na config; a agregação continua
determinística; o relatório marca o eval como **probabilístico** e recomenda revisar uma
amostra. ACs e NFRs nunca usam juiz LLM.

`sdd eval` fica fora do `sdd check` porque chama APIs de LLM (custo, tempo, segredo).
O workflow gerado traz o passo comentado.

## O que veio da TLC Spec-Driven

Ideias da [TLC Spec-Driven](https://agent-skills.techleads.club/tlc-spec-driven/)
(Felipe Rodrigues, Tech Leads Club), reimplementadas como verificação determinística:

| Ideia na TLC | Como ficou aqui |
|---|---|
| Profundidade ajustada à complexidade | `size` + `design_required_for` + trava no `diff` |
| Requirement closure gate | `open_questions` sem resposta bloqueiam o `validate` |
| Tabela de premissas | `assumptions` com padrão escolhido e justificativa obrigatórios |
| Decisões de projeto (AD-NNN) | `specs/decisions.yaml`, referências validadas |
| Discrimination sensor (LLM injeta falhas) | `sdd mutate`, mutação determinística |
| Fluxo por fases, testes derivados da spec, blast radius | `AGENTS.md` e constituição gerados |

**Não trouxemos:** o verificador LLM como aprovador (conflita com "nenhuma aprovação depende
de LLM"), a camada de lições aprendidas e a orquestração de sub-agentes (são processo do
agente, não verificação). Elas combinam bem com o sdd-kit se você usar a skill da TLC junto.

## Agnosticismo

- **De agente:** as instruções ficam em `AGENTS.md`. Se a sua ferramenta lê outro arquivo
  (ex.: `CLAUDE.md`), aponte-o para o `AGENTS.md` em vez de duplicar regras.
- **De linguagem:** o motor só conhece comandos de shell e JUnit XML.

## Limites conhecidos

- O rastreio prova que existe um teste **nomeado** para o AC e que ele passa. O `mutate`
  prova que os testes da feature detectam código errado, mas não que o teste do AC-001
  verifica exatamente o `then` do AC-001. Isso continua sendo revisão humana.
- A mutação é textual: pode gerar mutantes equivalentes (sobrevivem sem culpa dos testes),
  e só cobre operadores, não remoção de linhas ou troca de constantes. Execução interrompida
  à força (kill) pode deixar a cópia em `/tmp/sdd-mutate-*`.
- `size` é declarado por quem escreve a spec; a única trava objetiva é o número de arquivos.
- O `arch` lê imports como texto: não vê dependências indiretas (A importa B que importa
  infra), import dinâmico por string montada em tempo de execução, nem injeção por
  reflexão. Cobre o caso comum; para o resto, ferramentas dedicadas como gates.
- `dependencies` garante que o modo de falha foi **declarado e tem teste ligado**, não que
  o teste simula a falha de verdade. Revisão humana confere.
- O `eval` garante a aritmética e a integridade dos resultados, não a **qualidade do
  dataset**: um dataset fácil demais ou que não representa produção aprova um agente ruim.
  Também não impede um harness que grava `pass: true` sem chamar o modelo; isso é código
  revisável no PR, como qualquer teste.
- Evals no CI medem antes do merge. Deriva do modelo e comportamento em produção pedem
  observabilidade e evals contínuos sobre tráfego real, fora do escopo do kit.
- `invariants` e `out_of_scope` são documentados, não verificados.
- A seção `design` garante que a análise **existe e tem estrutura**, não que é **boa**:
  duas alternativas de fachada passam no validador, e `source` não prova que o número é real.
- Um NFR testado no CI aproxima, mas não substitui, medição em produção (SLO/observabilidade).
  Números sem `id` orientam o desenho mas não são verificados.
- O `diff` detecta divergência **por mudança** (código mexeu, spec não), não por conteúdo:
  qualquer edição na pasta da spec satisfaz a regra. O revisor ainda confere se a edição
  descreve a mudança. O trailer de exceção vale para o intervalo inteiro, não por feature.
- Sem orçamento de autonomia executável (hoje é texto na constituição) e sem
  `specify`/`plan` assistidos.

## Próximos passos sugeridos

1. Orçamento de autonomia executável: caminhos protegidos que exigem aprovação (CODEOWNERS).
2. Contratos: validar OpenAPI/JSON Schema contra a implementação como gate nativo.
3. Trailer por feature (`SDD-No-Spec-Change(pedidos): ...`) para exceções mais estreitas.

Este repositório se verifica: `sdd check` na raiz roda a spec em `specs/features/FEATURE-001`.
