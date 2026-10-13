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
small_max_files: 3         # feature small que altera mais arquivos reprova o diff

require_design: false      # camada design
design_required_for: [large, complex]
require_tasks: false       # camada tasks
tasks_required_for: [large, complex]
strict_criteria: false     # camada strict: critério vago vira erro

mutation:                  # camada mutate
  command: null            # padrão: tests.command (dica: algo que falhe rápido, ex. pytest -x)
  min_score: 0.8
  max_mutants: 50
  timeout: 120             # por mutante; estouro conta como morto
  extensions: [".py", ".ts", ".go", ...]
  link: [node_modules, .venv, venv]   # referenciados por symlink na cópia isolada
  env: {}                  # ex.: PYTHONPATH: "{root}/src" para pacote editável

evals:                     # camada evals
  command: null            # harness que grava .sdd/evals/<EVAL-ID>.jsonl
  results_dir: .sdd/evals
  timeout: 3600
  allow_llm_judge: false
```

## Camadas

| Camada | `sdd enable` cria ou altera | Para quê |
|---|---|---|
| `design` | `require_design` + seção no AGENTS.md | números, fluxo, alternativas, riscos e dependências em large/complex |
| `tasks` | `require_tasks` + seção | tarefas com origem, dependências e evidência |
| `constitution` | `specs/constitution.yaml` + seção | princípios com cobrança explícita |
| `arch` | `specs/architecture.yaml` + seção | regras de dependência entre camadas |
| `decisions` | `specs/decisions.yaml` + seção | decisões de projeto (AD-NNN) |
| `evals` | bloco `evals` + seção | comportamento de LLM com critério estatístico |
| `mutate` | bloco `mutation`, passo no CI + seção | força dos testes |
| `strict` | `strict_criteria: true` | critério vago reprova |
| `agentes` | `specs/agents.yaml` + seção | perfil de agentes (61 requisitos, módulo LGPD) |

Presets do `sdd init`: `minimo` (nenhuma camada), `padrao` (design, tasks, constitution,
arch, decisions) e `completo` (padrao + evals, mutate, strict).

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
