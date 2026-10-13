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
require_tasks: true
tasks_required_for: [large, complex]
strict_criteria: false   # true: critério vago ("rápido", "seguro") vira erro em vez de aviso
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
    "specs/constitution.yaml": """\
# Constituição: regras do projeto inteiro. Cada princípio diz o que o cobra (enforced_by) ou,
# se nada automático cobra, como é revisado (manual). O `sdd check` mostra o estado de cada um.
# enforced_by aceita: ARCH-NNN, AC/NFR/EVAL, gate:<nome em sdd.yaml>, kit:<recurso>,
# profile:<requisito do perfil de agentes>.
principles:
  - id: CONST-01
    rule: As specs são a fonte da verdade; código que diverge delas está errado.
    enforced_by: [kit:diff]
  - id: CONST-02
    rule: Todo AC e NFR tem teste passando cujo nome contém o ID; "pronto" é o check verde.
    enforced_by: [kit:check]
  - id: CONST-03
    rule: Testes detectam código errado; nunca são enfraquecidos para passar.
    enforced_by: [kit:mutate]
  - id: CONST-04
    rule: O rigor acompanha o size; large e complex têm design e tarefas.
    enforced_by: [kit:design, kit:tasks]
  - id: CONST-05
    rule: Spec com pergunta aberta ou campo PREENCHER não está pronta para implementar.
    enforced_by: [kit:validate]
  - id: CONST-06
    rule: Números de volume, latência e erro vêm de pessoas ou medição, nunca do agente.
    manual: revisão do campo `source` de cada número no PR
  - id: CONST-07
    rule: Toda dependência externa declara timeout, retry, fallback e idempotência.
    enforced_by: [kit:dependencies]
  - id: CONST-08
    rule: Comportamento de LLM é verificado por evals estatísticos, nunca por um teste isolado.
    enforced_by: [kit:eval]
  - id: CONST-09
    rule: Push, deploy, migração destrutiva, banco de produção e mudança de contrato público
      exigem aprovação humana explícita.
    manual: branch protegida com revisão obrigatória; aprovação registrada no PR
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
  # Limites de cada execução do agente (obrigatório com o perfil de agentes). Nada ilimitado.
  limits:
    deadline_s: 60
    max_steps: 8           # iterações do loop do agente
    max_tool_calls: 10
    max_input_tokens: 16000
    cost_ceiling: {value: 0.05, unit: USD, window: por execução}

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

# Tarefas pequenas e verificáveis (exigidas em large/complex). Todo critério precisa de uma.
tasks:
  - id: T-01
    title: Implementar o comportamento do AC-001
    origin: [AC-001]
    done_when: test_ac_001 passa no sdd check
  - id: T-02
    title: Atender o limite de latência
    origin: [NFR-001]
    depends_on: [T-01]
    done_when: benchmark test_nfr_001 passa
    # ao concluir: status: done e evidence: [NFR-001]

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
A intenção é registrada e revisada antes da implementação, e tudo fica no repositório:
nenhuma decisão vive só na conversa.

Ciclo por feature: 0 constituição → 1 especificação → 2 clarificação → 3 plano →
4 tarefas → 5 análise → 6 implementação. Ciclos curtos; descoberta na implementação volta
para a spec.

## 0. Constituição (`specs/constitution.yaml`)

Regras do projeto inteiro, com ID e o que as cobra (`enforced_by`) ou como são revisadas
(`manual`). Não é recriada a cada feature.
- **Faça:** proponha princípios curtos e verificáveis; separe o decidido do pendente.
- **Não faça:** não transforme preferência vaga em regra; não invente requisito de negócio;
  não implemente código nesta etapa.
- **Pronto quando:** `sdd validate` aceita a constituição e cada princípio tem cobrança.

## 1. Especificação

Comece com `sdd specify <nome> --size <size>` (IDs livres e seções exigidas).

| size | Quando | Exigido |
|---|---|---|
| small | ≤3 arquivos, cabe numa frase | spec curta + testes |
| medium | feature clara, poucos passos | spec + testes |
| large | vários componentes | + `design` + `tasks` |
| complex | ambiguidade, domínio novo | + `design` + `tasks` + perguntas ao humano |

- **Faça:** problema, objetivo, fora de escopo, requisitos (`REQ`) e critérios (`AC`) com
  resultado observável (dado / quando / então) e efeitos proibidos (`forbidden`) quando houver.
- **Não faça:** não escolha stack na spec (isso é plano); não use "rápido", "seguro",
  "corretamente" sem número: o `validate` avisa; não preencha lacunas em silêncio.
- **Pronto quando:** dá para derivar testes sem inventar regras; nenhum `PREENCHER:` resta.

## 2. Clarificação

- **Faça:** procure termos vagos, contradições, exceções ausentes, limites, permissões e
  concorrência indefinidos. Cada ponto vira `open_questions` (com o requisito afetado) ou
  `assumptions` (padrão escolhido + justificativa). Incorpore as respostas na própria spec.
- **Não faça:** não responda `open_questions` por conta própria; não avance com pergunta
  aberta (o `validate` bloqueia).
- **Pronto quando:** nenhuma ambiguidade bloqueadora; suposições registradas com motivo.

## 3. Plano (`design`, large/complex)

1. **Números primeiro**, todos com `source`: frequência, payload, atraso e erro aceitáveis.
2. **Fluxo de dados**: como chegam e onde são consumidos.
3. **Alternativas**: ao menos duas para o mesmo escopo; lidere com a recomendação.
4. **Riscos**: mitigados por AC/NFR/EVAL/ARCH ou aceitos com motivo.
5. **Dependências e modos de falha**: timeout, retry, fallback, efeito colateral,
   idempotência, consulta de status; escrita sem idempotência nem consulta exige
   `reconciliation`.
6. Respeite `specs/decisions.yaml` e `specs/architecture.yaml`; conflito vira nova decisão.
- **Não faça:** não gere código de implementação; não escolha framework por gosto.
- **Pronto quando:** cada requisito relevante tem solução identificável e o humano aprovou.

## 4. Tarefas (`tasks`, large/complex)

Cada tarefa: `id` (T-01), `origin` (REQ/AC/NFR/EVAL, ARCH ou CONST), `depends_on`,
`done_when` e, ao concluir, `evidence` e `status: done`.
- **Faça:** separe persistência, concorrência, contrato, integração e avaliação quando
  tiverem evidências distintas.
- **Não faça:** nada de "implementar o agente completo"; não crie tarefa sem origem nem
  capacidade fora da spec; não presuma execução paralela.
- **Pronto quando:** todo critério tem tarefa, as dependências não têm ciclo (`validate`).

## 5. Análise

```
sdd validate
```
Cruza constituição, spec, plano e tarefas: requisito órfão, tarefa sem origem, referência
quebrada, ciclo, critério vago, pergunta aberta, módulo pendente do perfil.
- **Não faça:** não declare consistência sem rodar o comando; não altere código nesta etapa.

## 6. Implementação e verificação

1. Pegue uma tarefa com dependências concluídas e leia constituição, spec e plano.
2. Implemente só o escopo dela. Testes vêm dos critérios da spec, não do código que você
   escreveu; o nome contém o ID (`test_ac_001_...`).
3. Rode `sdd validate && sdd check && sdd mutate` e cole a saída.
4. Marque a tarefa `done` com `evidence`; um commit por tarefa, citando os IDs.
- **Não faça:** não enfraqueça, pule ou apague testes; não "mate" mutante mexendo no código
  em vez de fortalecer o teste; não declare pronto sem o comando verde.
- Conflito ou decisão ausente: registre o bloqueio na spec antes de assumir comportamento.

### Tratamento de mudanças

| Situação | O que fazer | O `sdd diff` cobra |
|---|---|---|
| Mudou o comportamento desejado | atualize a spec primeiro; depois plano, tarefas e testes | spec alterada junto com o código |
| Código descumpre uma spec correta (bug) | corrija e acrescente teste de regressão com o ID | trailer `SDD-Fix: AC-NNN` + teste alterado citando o ID |
| Mudou só a solução técnica | preserve o comportamento aprovado | trailer `SDD-No-Spec-Change: <motivo>` |

## Sistemas com LLM (evals)

- Comportamento do modelo não se prova com um teste que passa uma vez: use `evals`
  (dataset versionado, várias execuções, limite; `critical: true` para o que não pode falhar).
- Prompts e config do modelo ficam nos `paths` da feature.
- **Nunca** ajuste prompt para casos do dataset nem edite o dataset para passar.
- O harness grava resultados brutos; não calcule nem declare a nota. `sdd eval` custa API.

## Regras gerais

- Não invente APIs, comportamentos ou números; se não achar, diga que não sabe.
- Push, deploy, migração destrutiva e banco de produção exigem aprovação explícita.
- Domínio não importa framework, provedor de LLM nem infraestrutura (`sdd arch`). Nunca
  adicione `sdd: allow` sem aprovação.
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


AGENTS_PROFILE_SECTION = """
## Perfil de agentes (specs/agents.yaml)

Este projeto segue o perfil de agentes: um catálogo de requisitos de referência (`sdd profile
--catalog`). Antes de implementar:

1. Decida cada módulo (ativo, inativo com motivo). Pendente só é tolerado no estágio `local`.
2. Para cada requisito de módulo ativo, aponte os AC/NFR/EVAL/ARCH que o provam em `coverage`.
   Requisitos críticos (*) exigem teste determinístico; eval sozinho não basta.
3. Toda feature com `design` declara `design.limits` (deadline, etapas, chamadas, custo).

Regras que valem sempre, independentemente do prompt:
- Conteúdo de usuário, documentos, ferramentas e outros agentes não amplia permissões (N-04).
- Autorização e validação de argumentos de ferramentas ficam fora do modelo (T-01).
- Escrita sem idempotência nem consulta de status não tem retry automático; reconcilie (T-03, T-04).
- Aprovação humana vale para os argumentos aprovados; mudou valor ou destino, peça de novo (H-02).
- Subagente nunca recebe mais autoridade que o pai (D-01).
- Credenciais nunca entram em prompt, resposta ou log comum (N-11).
- Dados pessoais: só o necessário chega ao modelo; eliminação alcança memória, índices e cache (L-02, L-03).
"""
