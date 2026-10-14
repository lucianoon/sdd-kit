"""Arquivos de `sdd init` e camadas de `sdd enable`.

Adoção gradual: o nível mínimo traz só spec, check e diff. Cada camada (design, tarefas,
constituição, arquitetura, decisões, evals, mutação, critério estrito, perfil de agentes)
acrescenta arquivos, chaves de configuração e uma seção ao AGENTS.md quando for ligada.
"""
from __future__ import annotations

PRESETS = {
    "minimo": [],
    "padrao": ["design", "tasks", "constitution", "arch", "decisions"],
    "completo": ["design", "tasks", "constitution", "arch", "decisions", "evals", "mutate", "strict"],
}
LAYERS = ("design", "tasks", "constitution", "arch", "decisions", "evals", "mutate", "strict", "agentes")

CONFIG = """\
# sdd-kit. Ligue mais camadas com `sdd enable <camada>`; referência em docs/configuracao.md.
version: 1
tests:
  # Qualquer runner que gere JUnit XML: pytest, jest, vitest, go test (+ go-junit-report), maven...
  command: "pytest -q --junitxml=.sdd/junit.xml"
  junit: ".sdd/junit.xml"
# Código de produção. Arquivo alterado aqui sem feature dona reprova o `sdd diff`.
code: []
  # - src/**
"""

# Chaves que cada camada acrescenta ao specs/sdd.yaml (só se ainda não existirem).
CONFIG_LAYERS = {
    "design": """
# camada design: specs large/complex precisam da seção `design`
require_design: true
design_required_for: [large, complex]
""",
    "tasks": """
# camada tasks: specs large/complex precisam de `tasks`
require_tasks: true
tasks_required_for: [large, complex]
""",
    "strict": """
# camada strict: critério vago ("rápido", "seguro") sem número vira erro
strict_criteria: true
""",
    "mutate": """
# camada mutate: `sdd mutate` injeta falhas no código e cobra que os testes as peguem
mutation:
  min_score: 0.8
  max_mutants: 50
  timeout: 120
  # command: "pytest -q -x"     # mais rápido que tests.command
""",
    "evals": """
# camada evals: `sdd eval` aplica critérios estatísticos a comportamento de LLM
evals:
  # command: "python evals/run.py"   # grava .sdd/evals/<EVAL-ID>.jsonl
  allow_llm_judge: false
""",
}

SPEC_MIN = """\
feature: exemplo
version: 1
size: small            # small | medium | large | complex
summary: Substitua por uma feature real (ou crie outra com `sdd specify <nome>`).
requirements:
  - id: REQ-001
    description: Descreva o comportamento esperado.
    acceptance:
      - id: AC-001
        given: um estado inicial
        when: uma ação acontece
        then: um resultado observável
# Código desta feature: mudou aqui sem mudar a spec? `sdd diff` reprova.
paths: []
  # - src/exemplo/**
"""

SPEC_FULL = """\
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
"""

FILES_LAYERS = {
    "constitution": ("specs/constitution.yaml", """\
# Constituição: regras do projeto inteiro. Cada princípio diz o que o cobra (enforced_by) ou,
# se nada automático cobra, como é revisado (manual). O `sdd check` mostra o estado de cada um.
# enforced_by aceita: ARCH-NNN, AC/NFR/EVAL, gate:<nome em sdd.yaml>, kit:<recurso>,
# profile:<requisito do perfil de agentes>.
principles:
  - id: CONST-01
    rule: As specs são a fonte da verdade; código que diverge delas está errado.
    enforced_by: [kit:diff]
  - id: CONST-02
    rule: Todo AC e NFR tem teste passando cujo nome contém o ID; o check verde aprova seu alcance declarado.
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
    rule: Comportamento de LLM exige evals estatísticos; juiz LLM precisa de política explícita e evidência marcada como probabilística.
    enforced_by: [kit:eval]
  - id: CONST-09
    rule: Push, deploy, migração destrutiva, banco de produção e mudança de contrato público
      exigem aprovação humana explícita.
    manual: branch protegida com revisão obrigatória; aprovação registrada no PR
"""),
    "decisions": ("specs/decisions.yaml", """\
# Decisões de projeto que valem para todas as features. Specs as referenciam em `decisions`.
# Decisão substituída: status: superseded + superseded_by. Nunca apague; o histórico importa.
decisions:
  - id: AD-001
    title: Specs são a fonte da verdade
    decision: Comportamento é definido em specs/; código que diverge está errado.
    rationale: Agentes de IA não guardam contexto entre sessões; o repositório guarda.
"""),
    "arch": ("specs/architecture.yaml", """\
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
"""),
}

AGENTS_CORE = """\
# Instruções para agentes de IA

Este repositório segue SDD (Specification-Driven Development). Você decide **como**
implementar; a spec decide **o que** é correto; o `sdd` decide se está pronto.
Nenhuma decisão vive só na conversa: o que importa fica no repositório.

## Fluxo

1. **Spec primeiro.** `sdd specify <nome> --size <small|medium|large|complex>` cria o
   esqueleto com IDs livres. Troque cada `PREENCHER:` por conteúdo real.
2. **Critérios observáveis.** Dado / quando / então, com número quando houver medida.
   "Rápido", "seguro" e "corretamente" sem número não são critério.
3. **Ambiguidade vira pergunta.** Registre em `open_questions`; não responda sozinho.
   Lacuna resolvida por padrão vira `assumptions`, com justificativa.
4. **Testes vêm dos critérios**, não do código que você escreveu. O nome do teste contém
   o ID: `test_ac_001_...`, `it("AC-001 ...")`, `TestAC001...`.
5. **Verifique o alcance.** Rode `sdd validate && sdd check` e cole a saída. Execute
   também diff, mutate e eval quando aplicáveis; princípios PENDENTE exigem verificação própria.

## Mudanças

| Situação | O que fazer | No commit |
|---|---|---|
| Mudou o comportamento | atualize a spec junto com o código | — |
| Bug (código descumpre spec correta) | corrija e adicione teste de regressão com o ID | `SDD-Fix: AC-NNN` |
| Só a solução técnica mudou | preserve o comportamento | `SDD-No-Spec-Change(nome-da-feature): <motivo>` |

## Nunca

- Enfraquecer, pular ou apagar testes para passar, nem editar a spec para isso.
- Inventar APIs, comportamentos ou números; se não souber, diga.
- Push, deploy, migração destrutiva ou banco de produção sem aprovação explícita.
"""

AGENTS_LAYERS = {
    "design": """
<!-- sdd:design -->
## Plano (`design`, specs large/complex)

Antes de codar, com aprovação humana: números com `source` (nunca inventados), fluxo de
dados, ao menos duas alternativas, riscos mitigados por teste ou aceitos com motivo, e
cada dependência externa com timeout, retry, fallback e idempotência. Escrita sem
idempotência nem consulta de status precisa de `reconciliation`.
""",
    "tasks": """
<!-- sdd:tasks -->
## Tarefas (`tasks`, specs large/complex)

Unidades pequenas com `origin` (REQ/AC/NFR/EVAL, ARCH ou CONST), `depends_on` e
`done_when`. Todo critério precisa de uma tarefa. Ao concluir: `status: done` com
`evidence`. Nada de "implementar tudo" numa tarefa só, nem tarefa sem origem.
""",
    "constitution": """
<!-- sdd:constitution -->
## Constituição (`specs/constitution.yaml`)

Regras do projeto inteiro, cada uma com o que a cobra (`enforced_by`) ou como é revisada
(`manual`). Leia antes de cada feature; conflito com ela é bloqueio, não exceção.
""",
    "arch": """
<!-- sdd:arch -->
## Arquitetura (`specs/architecture.yaml`)

Domínio não importa framework, provedor de LLM nem infraestrutura: dependa de interfaces
e implemente adapters. `sdd arch` verifica. Nunca adicione `sdd: allow` sem aprovação.
""",
    "decisions": """
<!-- sdd:decisions -->
## Decisões (`specs/decisions.yaml`)

Decisões ativas valem para todas as features. Conflito? Proponha uma nova decisão que
substitua a antiga (`superseded_by`); não a ignore em silêncio.
""",
    "evals": """
<!-- sdd:evals -->
## Comportamento de LLM (`evals`)

Um teste que passa uma vez não prova comportamento de modelo: use evals com dataset
versionado, várias execuções e limite (`critical: true` para o que não pode falhar).
Nunca ajuste prompt para casos do dataset nem edite o dataset para passar. O harness grava
resultados brutos; a nota é do `sdd eval`.
""",
    "mutate": """
<!-- sdd:mutate -->
## Força dos testes (`sdd mutate`)

Mutante sobrevivente é asserção fraca: fortaleça o teste; não mexa no código para
"matar" o mutante.
""",
    "strict": "",
    "agentes": """
<!-- sdd:agentes -->
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
""",
}

WORKFLOW = """\
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
__MUTATE_STEP__      - if: always()
        run: cat .sdd/report.md >> "$GITHUB_STEP_SUMMARY" 2>/dev/null || true
"""

MUTATE_STEP = """\
      - if: github.event_name == 'pull_request'
        run: sdd mutate --base "origin/${{ github.base_ref }}"
"""


def initial_files(preset: str = "minimo") -> dict[str, str]:
    """Arquivos base do init. As camadas do preset são aplicadas depois, por `apply_layer`."""
    layers = PRESETS[preset]
    return {
        "specs/sdd.yaml": CONFIG,
        "specs/features/FEATURE-001/spec.yaml": SPEC_FULL if "design" in layers else SPEC_MIN,
        "AGENTS.md": AGENTS_CORE,
        ".github/workflows/sdd.yml": WORKFLOW.replace("__MUTATE_STEP__", MUTATE_STEP if "mutate" in layers else ""),
    }
