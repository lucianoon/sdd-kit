# Configuração (`specs/sdd.yaml`)

Só `tests` é obrigatório. Tudo o mais é opcional e tem padrão conservador. O `sdd enable
<camada>` acrescenta as chaves de cada camada por você.

```yaml
version: 1

tests:
  command: "pytest -q --junitxml=.sdd/junit.xml"   # qualquer runner que gere JUnit XML
  junit: ".sdd/junit.xml"
  timeout: 3600                                    # segundos (testes e gates)
  paths: ["tests/**", "**/*_test.go", ...]         # onde ficam os testes (para SDD-Fix)

gates:                     # comandos extras; reprovam se o exit code for diferente de 0
  type_check: "mypy src"

code: ["src/**"]           # código de produção: arquivo aqui sem feature dona reprova o diff
allow_global_diff_override: false  # migração temporária do trailer global; veja verificacao.md
small_max_files: 3         # feature small que altera mais arquivos reprova o diff

require_design: false      # camada design
design_required_for: [large, complex]
require_tasks: false       # camada tasks
tasks_required_for: [large, complex]
strict_criteria: false     # camada strict: critério vago vira erro
require_approval: false    # camada approval: spec e plano aprovados antes de implementar
approval_required_for: [medium, large, complex]

mutation:                  # camada mutate
  command: null            # padrão: tests.command (dica: algo que falhe rápido, ex. pytest -x)
  min_score: 0.8
  max_mutants: 50
  timeout: 120             # por mutante; estouro conta como morto
  build: null              # ex.: "tsc --noEmit"; falha = mutante inválido, fora do score
  extensions: [".py", ".ts", ".go", ...]
  link: [node_modules, .venv, venv]   # referenciados por symlink na cópia isolada
  env: {}                  # ex.: PYTHONPATH: "{root}/src" para pacote editável

evals:                     # camada evals
  command: null            # harness que grava .sdd/evals/<EVAL-ID>.jsonl
  results_dir: .sdd/evals
  timeout: 3600
  allow_llm_judge: false

review:                    # revisão escalonada por risco; veja revisao.md
  tiers: {}                # globs por tier: {low: [...], medium: [...], high: [...]}
  default_tier: medium     # arquivo alterado que não casa nenhum glob
  approvals: {low: 0, medium: 1, high: 2}   # aprovações humanas; não pode diminuir com o tier
  trusted_authors: []      # vazio: sem restrição; fora da lista, mínimo de 1 aprovação
  escalations: .sdd/review/escalations.json # pedidos externos que só elevam o tier
  allow_llm_findings: false
  findings: .sdd/review/findings.json       # achados de revisor LLM externo
  max_rounds: 3            # teto de rodadas revisão/correção
  human_adequacy: []       # features (nome ou glob) cuja adequação exige revisor humano
```

O mutate define `TMPDIR`, `TEMP` e `TMP` privados à cópia, substituindo esses três
valores também quando aparecem em `mutation.env`. Os demais valores são preservados.

Números devem ser finitos. Chaves YAML duplicadas reprovam. `tests.junit`, datasets e
`evals.results_dir` usam caminhos relativos com `/`, sem drives, `..` ou barras invertidas.
A gravação de artefatos recusa links e usa substituição atômica. Veja
[garantias e migração](arquitetura-interna.md).

## Camadas

| Camada | `sdd enable` cria ou altera | Para quê |
|---|---|---|
| `design` | `require_design` + seção no AGENTS.md | números, fluxo, alternativas, riscos e dependências em large/complex |
| `tasks` | `require_tasks` + seção | tarefas com origem, dependências e evidência |
| `constitution` | `specs/constitution.yaml` + seção | princípios com cobrança explícita |
| `arch` | `specs/architecture.yaml` + seção | regras de dependência entre camadas |
| `decisions` | `specs/decisions.yaml` + seção | decisões de projeto (AD-NNN) |
| `approval` | `require_approval` + seção | spec e plano aprovados pelo usuário (`sdd approve`) antes de implementar |
| `evals` | bloco `evals` + seção | comportamento de LLM com critério estatístico |
| `mutate` | bloco `mutation`, passo no CI + seção | força dos testes |
| `strict` | `strict_criteria: true` | critério vago reprova |
| `agentes` | `specs/agents.yaml` + seção | perfil de agentes (61 requisitos, módulo LGPD) |

Presets do `sdd init`: `minimo` (nenhuma camada), `padrao` (design, tasks, constitution,
arch, decisions, approval) e `completo` (padrao + evals, mutate, strict).

## Arquivos em `specs/`

| Arquivo | Obrigatório | Conteúdo |
|---|---|---|
| `sdd.yaml` | sim | esta configuração |
| `features/*/spec.yaml` | sim | uma spec por feature ([especificação](especificacao.md)) |
| `constitution.yaml` | não | princípios ([arquitetura e constituição](arquitetura.md)) |
| `architecture.yaml` | não | regras ARCH ([arquitetura e constituição](arquitetura.md)) |
| `decisions.yaml` | não | decisões AD-NNN ([especificação](especificacao.md)) |
| `agents.yaml` | não | perfil de agentes ([agentes](agentes.md)) |

O JSON Schema da spec sai com `sdd schema` (útil para autocompletar no editor).
