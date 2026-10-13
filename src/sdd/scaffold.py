"""Arquivos criados por `sdd init`."""

FILES = {
    "specs/sdd.yaml": """\
# Configuração do motor de verificação. Único ponto que conhece a sua stack.
version: 1
tests:
  # Qualquer runner serve, desde que gere JUnit XML (pytest, jest, go test, maven...).
  command: "pytest -q --junitxml=.sdd/junit.xml"
  junit: ".sdd/junit.xml"
gates: {}
  # type_check: "mypy src"
  # security_scan: "bandit -q -r src"
# Código de produção. Arquivo alterado aqui sem feature dona reprova o `sdd diff`.
code: []
  # - src/**

# Rigor proporcional ao tamanho: `design` só é exigido para estes sizes.
require_design: true
design_required_for: [large, complex]
# Feature `small` que altera mais arquivos de código que isto reprova o `sdd diff`.
small_max_files: 3

# sdd mutate: injeta falhas no código das features e cobra que os testes as peguem.
mutation:
  min_score: 0.8
  max_mutants: 50
  timeout: 120          # segundos por mutante; estouro conta como morto
  # command: "pytest -q -x"   # padrão: tests.command. Falhar rápido acelera muito.
  # env:
  #   PYTHONPATH: "{root}/src"  # se o pacote estiver instalado em modo editável

# sdd eval: critérios estatísticos para comportamento de LLM (EVAL-NNN nas specs).
# O harness grava <results_dir>/<EVAL-ID>.jsonl, uma linha por caso e execução:
#   {"case": "<id do dataset>", "run": 1, "pass": true}    ou    {..., "score": 0.82}
evals:
  # command: "python evals/run.py"
  results_dir: .sdd/evals
  timeout: 3600
  allow_llm_judge: false   # true permite evals com judge: llm (marcadas no relatório)
""",
    "specs/decisions.yaml": """\
# Decisões de projeto que valem para todas as features. Specs as referenciam em `decisions`.
# Decisão substituída: status: superseded + superseded_by. Nunca apague; o histórico importa.
decisions:
  - id: AD-001
    title: Specs são a fonte da verdade
    decision: Comportamento é definido em specs/; código que diverge está errado.
    rationale: Agentes de IA não guardam contexto entre sessões; o repositório guarda.
""",
    "specs/architecture.yaml": """\
# Regras de dependência entre camadas, verificadas pelo `sdd check` (e `sdd arch`).
# Lê os imports de Python, JS/TS e Go. Exceção pontual, na própria linha do import:
#   import openai  # sdd: allow ARCH-001 adapter legado, migração em AD-007
# (sem motivo, a marcação não vale)
rules: []
  # Hexagonal / Clean Architecture: o domínio não conhece framework nem provedor.
  # Assim o provedor de LLM, o orquestrador e o banco trocam sem reescrever o negócio.
  # - id: ARCH-001
  #   description: Domínio não depende de infraestrutura nem de provedores de IA
  #   from: ["src/domain/**"]
  #   forbid: [openai, anthropic, "langchain*", "langgraph*", "@langchain/*", redis, sqlalchemy, boto3]
  #   forbid_paths: ["src/adapters/**", "src/infra/**"]
  #
  # - id: ARCH-002
  #   description: Tools só chegam ao LLM pelo adapter, nunca direto da API HTTP
  #   from: ["src/api/**"]
  #   forbid_paths: ["src/adapters/llm/**"]
""",
    "specs/constitution.md": """\
# Constituição do projeto

Regras que valem para qualquer agente e qualquer pessoa.

1. As specs em `specs/` são a fonte da verdade. Código que diverge delas está errado.
2. Mudou o comportamento? Mude a spec no mesmo commit.
   Refatoração sem mudança de comportamento declara no commit:
   `SDD-No-Spec-Change: <motivo>`.
3. Todo `AC-NNN` e `NFR-NNN` tem ao menos um teste cujo nome contém o ID.
4. "Pronto" significa `sdd check` verde, não uma resposta convincente.
   Quem escreveu o código não é quem decide se está correto.
5. O rigor acompanha o tamanho (`size`). Features `large`/`complex` têm `design`:
   números com fonte, fluxo de dados, ao menos duas alternativas e riscos tratados.
6. Números de volume, latência e erro vêm de pessoas ou de medição. Agente não inventa.
7. Spec com pergunta aberta não está pronta para implementar.
   Dependências entre camadas seguem `specs/architecture.yaml`; toda dependência externa
   declara timeout, retry, fallback e idempotência.
   Comportamento de LLM é verificado por `evals` estatísticos, nunca por um teste isolado;
   o dataset de um eval só muda junto com a spec.
8. Exigem aprovação humana explícita: push, deploy, migrações destrutivas, banco de
   produção, mudança de contrato público, segredos/permissões, remoção ou
   enfraquecimento de testes.
""",
    "specs/features/FEATURE-001/spec.yaml": """\
feature: exemplo
version: 1
# small (≤3 arquivos, uma frase) | medium (feature clara) | large (vários componentes)
# | complex (ambiguidade, domínio novo). Define o rigor exigido. Padrão: large.
size: large
summary: Substitua por uma feature real.
out_of_scope: []

# Lacunas da spec resolvidas com um padrão escolhido. Nada de suposição silenciosa.
assumptions:
  - assumption: formato da moeda não foi especificado
    chosen: BRL com 2 casas decimais
    rationale: único mercado atendido hoje (substitua)
# Pergunta sem `answer` bloqueia o `sdd validate`.
open_questions: []
  # - question: o pedido pode ser editado depois de pago?
  #   answer: não; vira cancelamento + novo pedido
decisions: [AD-001]       # decisões de specs/decisions.yaml que esta feature segue

requirements:
  - id: REQ-001
    description: Descreva o comportamento esperado.
    acceptance:
      - id: AC-001
        given: um estado inicial
        when: uma ação acontece
        then: um resultado observável

# Desenho arquitetural (exigido para large/complex). Números vêm de gente, não do agente.
design:
  numbers:
    # Com `id`, vira NFR: exige teste/benchmark com o ID no nome (ex.: test_nfr_001_...).
    - id: NFR-001
      metric: latency_p95
      max: 200
      unit: ms
      at: 50 req/s de pico
      source: estimativa do PO (substitua)
    # Sem `id`: orienta o desenho, mas não é verificado no check.
    - metric: payload
      max: 64
      unit: KB
      source: contrato com o cliente (substitua)
    - metric: error_rate
      max: 0.1
      unit: "%"
      source: SLA (substitua)
  data_flow:
    ingress:
      - via: http          # http | stream | arquivo | fila ...
        source: app mobile
        frequency: 50 req/s de pico, 5 req/s em média
    egress:
      - to: postgres       # banco analítico | cache em memória | API ...
        consumers: [dashboard financeiro]
        freshness: até 5 min
  alternatives:            # mínimo 2, exatamente 1 escolhida
    - name: API síncrona + postgres
      chosen: true
      why: volume baixo; menos peças para operar
    - name: fila + worker assíncrono
      why_not: complexidade sem ganho no volume atual
  risks:                   # cada um: mitigated_by (AC/NFR desta spec) ou accepted (motivo)
    - area: performance
      severity: medium
      description: pico de fim de mês dobra o tráfego
      mitigated_by: [NFR-001]
    - area: security
      severity: low
      description: exemplo de risco aceito
      accepted: substitua por um risco real ou remova
  # Toda dependência externa: como se comporta quando falha. `[]` afirma que não há nenhuma.
  dependencies:
    - name: provedor de LLM
      kind: llm            # llm | vector_store | database | cache | queue | external_api | tool | process
      timeout_ms: 30000
      retry: {max_attempts: 3, backoff: exponential}
      fallback: modelo secundário; se também falhar, resposta padrão e handoff humano
      side_effects: false  # escreve, cobra, envia, cria pedido?
      idempotent: true     # repetir dá o mesmo efeito? retry + efeito colateral exige true
      covered_by: [AC-001] # AC/NFR/EVAL que testam a falha (substitua)

# Comportamento de LLM: critério estatístico sobre um dataset versionado (sdd eval).
evals: []
  # - id: EVAL-001
  #   metric: tool_selection_accuracy
  #   description: o agente escolhe a tool certa para o pedido
  #   dataset: evals/datasets/tools.jsonl   # JSONL, cada linha com "id" único
  #   min_cases: 200                        # casos distintos em cada execução
  #   runs: 3                               # execuções independentes
  #   aggregate: pass_rate                  # ou mean_score (campo "score")
  #   threshold: {min: 0.9}
  #   max_run_spread: 0.05                  # estabilidade entre execuções
  #   use_lower_bound: true                 # compara o limite inferior do IC 95%
  #   judge: deterministic                  # ou llm (exige allow_llm_judge)

invariants: []
quality_gates: []
# Código que pertence a esta feature. Mudou aqui sem mudar a spec? `sdd diff` reprova.
# Também é o alvo do `sdd mutate`. Inclua prompts e config do modelo: trocar prompt
# sem atualizar a spec é a regressão silenciosa mais comum em agentes.
paths: []
  # - src/exemplo/**
""",
    "AGENTS.md": """\
# Instruções para agentes de IA

Este repositório segue SDD (Specification-Driven Development). Você decide **como**
implementar; a spec decide **o que** é correto; o `sdd` decide se está pronto.

Leia `specs/constitution.md`, `specs/decisions.yaml` e a spec da feature antes de agir.

## 0. Dimensione

Classifique a mudança e registre em `size`. O rigor acompanha o tamanho:

| size | Quando | Exigido |
|---|---|---|
| small | ≤3 arquivos, cabe numa frase | spec curta + testes |
| medium | feature clara, poucos passos | spec + testes |
| large | vários componentes | + `design` + tarefas explícitas |
| complex | ambiguidade, domínio novo | + `design` + pesquisa + perguntas ao humano |

Na dúvida, escolha o maior. O `sdd diff` reprova `small` que altera mais de 3 arquivos.

## 1. Especifique

- Comece com `sdd specify <nome> --size <size>`: gera o esqueleto com IDs livres e as
  seções exigidas. Troque cada `PREENCHER` por conteúdo real; o `sdd validate` aponta o que falta.
- Requisitos com IDs (`REQ-NNN`) e critérios testáveis (`AC-NNN`): dado / quando / então.
- Liste o que está **fora de escopo**.
- Toda lacuna vira `assumptions` (padrão escolhido + justificativa) ou `open_questions`.
- Dimensões que costumam esconder requisitos implícitos: persistência, chamadas externas,
  autenticação, pagamentos, concorrência, transições de estado. Se a feature toca alguma,
  pergunte ao humano antes de seguir.
- Pergunta aberta sem `answer` bloqueia o `sdd validate`. Não responda por conta própria.

## 2. Desenhe (large/complex)

1. **Números primeiro.** Pergunte: frequência de chegada, tamanho do payload, atraso
   aceitável, taxa de erro aceitável. Não invente; todo número tem `source`.
2. **Fluxo de dados.** Como chegam (HTTP, stream, arquivo) e onde são consumidos.
3. **Alternativas.** Ao menos duas, entregando o mesmo escopo. Lidere com a recomendação.
4. **Riscos.** Cada um mitigado por um AC/NFR testável ou aceito com motivo escrito.
5. **Modos de falha.** Para cada dependência externa (LLM, banco, fila, API, tool):
   timeout, retry, fallback, se tem efeito colateral e se é idempotente. Retry em operação
   com efeito colateral exige idempotência (ex.: chave de idempotência); o validador cobra.
   Cada dependência aponta para os testes que simulam a falha (`covered_by`).
6. Respeite as decisões ativas em `specs/decisions.yaml`. Conflito? Proponha uma nova
   decisão que substitua a antiga; não a ignore em silêncio.
7. Apresente o `design` para aprovação humana antes de escrever código.

## 3. Quebre em tarefas (large/complex)

Tarefas pequenas, com dependências explícitas, cada uma citando os IDs que entrega
e com seus testes junto. Mais de ~5 passos numa feature medium? Ela era large.

## 4. Implemente

- Uma tarefa por vez. Os testes vêm dos critérios da spec, não do código que você escreveu:
  assertam o resultado definido na spec.
- Nome do teste contém o ID: `test_ac_001_pedido_persistido`, `test_nfr_001_p95_abaixo_de_200ms`.
- Um commit por tarefa, citando os IDs. Nunca enfraqueça, pule ou apague testes para passar.
- Mudou código em `paths` de uma feature? Atualize a spec dela no mesmo PR.
- `SDD-No-Spec-Change: <motivo>` só para refatoração sem mudança de comportamento.

## 5. Verifique (não é você quem aprova)

```
sdd validate && sdd check && sdd mutate
```

- `sdd check`: todo AC/NFR tem teste passando.
- `sdd mutate`: os testes pegam código errado. Mutante sobrevivente = asserção fraca;
  fortaleça o teste, não mexa no código para "matar" o mutante.
- Cole a saída. "Pronto" é o comando verde, não a sua avaliação.

## Sistemas com LLM (evals)

- Comportamento do modelo (escolha de tool, qualidade, alucinação) não se prova com um teste
  que passa uma vez. Use `evals` na spec: dataset versionado, várias execuções, limite.
- Prompts e config do modelo ficam nos `paths` da feature: trocá-los exige atualizar a spec.
- **Nunca** ajuste prompt para casos específicos do dataset, nem edite o dataset para passar.
  Mudar o dataset é mudar a régua: exige mudança na spec e aprovação humana (`sdd diff` cobra).
- O harness grava resultados brutos por caso; não calcule nem declare a nota final.
- Rode `sdd eval` (custa chamadas de API; avise antes de rodar datasets grandes).

## Regras gerais

- Não invente APIs, comportamentos ou números. Procure no código, na documentação do projeto
  e na documentação oficial; se não achar, diga que não sabe.
- Push, deploy, migração destrutiva e banco de produção exigem aprovação explícita
  para aquela ação; aprovar a spec não autoriza nada disso.
- Respeite `specs/architecture.yaml`: domínio não importa framework, provedor de LLM nem
  infraestrutura; dependa de interfaces (ports) e implemente adapters. `sdd arch` verifica.
  Nunca adicione `sdd: allow` sem pedir aprovação; a exceção fica registrada no relatório.
""",
    ".github/workflows/sdd.yml": """\
name: sdd
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with: { fetch-depth: 0 }   # sdd diff precisa do histórico
      - uses: actions/setup-python@v6
        with: { python-version: "3.12" }
      # Instale aqui as dependências do seu projeto.
      - run: pip install "git+https://github.com/lucianoon/sdd-kit"
      - run: sdd validate
      - if: github.event_name == 'pull_request'
        run: sdd diff --base "origin/${{ github.base_ref }}"
      - run: sdd check
      # Mutação só no que mudou no PR, para caber no tempo do CI.
      - if: github.event_name == 'pull_request'
        run: sdd mutate --base "origin/${{ github.base_ref }}"
      # Evals chamam APIs de LLM: exigem secret e custam. Habilite quando houver harness.
      # - if: github.event_name == 'pull_request'
      #   run: sdd eval
      #   env: { ANTHROPIC_API_KEY: "${{ secrets.ANTHROPIC_API_KEY }}" }
      - if: always()
        run: cat .sdd/report.md .sdd/mutation.md .sdd/eval.md >> "$GITHUB_STEP_SUMMARY" 2>/dev/null || true
""",
}
