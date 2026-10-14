# sdd-kit

[![ci](https://github.com/lucianoon/sdd-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/lucianoon/sdd-kit/actions/workflows/ci.yml)

**Specification-Driven Development para desenvolvimento assistido por IA, com verificação
por ferramentas independentes.**

O agente (Claude Code, Codex, Cursor, Copilot...) escolhe **como** implementar. A spec
define **o que** é correto. O `sdd` decide se está **pronto**, rodando fora do LLM, na sua
máquina e no CI.

> LLMs propõem e implementam. Especificações definem os contratos.
> Ferramentas independentes verificam. Humanos governam as decisões de maior risco.

A maioria das abordagens de SDD para IA organiza prompts e templates e confia que o agente
seguiu o processo. O sdd-kit **verifica**: cada critério precisa de um teste real passando,
código não muda sem a spec mudar junto, testes fracos são expostos por mutação, e
comportamento de LLM é medido com critério estatístico. Checks de código usam ferramentas
externas ao agente. Evals com juiz LLM exigem política explícita e são identificadas como
evidência probabilística.

## Instalação

```bash
pipx install sdd-kit-ai                                  # do PyPI
pipx install git+https://github.com/lucianoon/sdd-kit    # da fonte, sempre atualizado
```

Python 3.10+. Funciona com qualquer linguagem cujo runner de testes gere JUnit XML
(pytest, jest, vitest, Go, JUnit...); veja [`examples/`](examples/).

## Começo em 5 minutos

```bash
sdd init                                   # 4 arquivos: config, spec de exemplo, AGENTS.md, CI
sdd specify criar-pedido --acs 2           # esqueleto da spec com IDs livres
# preencha os campos marcados com PREENCHER:, escreva os testes com o ID no nome
sdd validate && sdd check                  # pronto = verde
```

```
$ sdd specify criar-pedido --acs 2
criado   specs/features/FEATURE-002/spec.yaml
IDs      REQ: REQ-002  AC: AC-002, AC-003
```

```python
def test_ac_002_pedido_persistido(): ...   # o ID do critério no nome liga teste e spec
```

```
$ sdd check
OK         AC-002   criar-pedido: pedido é persistido
SEM_TESTE  AC-003   criar-pedido: pedido é rejeitado
ERRO  AC-003 (criar-pedido): SEM_TESTE

REPROVADO — relatório em .sdd/report.md
```

## Adote aos poucos

Comece no mínimo e ligue camadas quando fizerem sentido:

```bash
sdd init --preset minimo      # spec, check e diff (padrão)
sdd init --preset padrao      # + design, tarefas, constituição, arquitetura, decisões
sdd init --preset completo    # + evals, mutação, critério estrito

sdd enable design tasks       # liga camadas num projeto existente
sdd enable agentes            # perfil de agentes de IA (61 requisitos, incluindo LGPD)
```

## Aplicações de agentes de IA

`sdd enable agentes` (ou `sdd init --profile agentes`) traz um catálogo de requisitos de
referência para agentes, derivado da *SPEC-BASE v0.1*: 12 módulos (núcleo, ferramentas e
efeitos, recuperação, memória, humano no laço, delegação, produção, LGPD/PL 2338...),
61 requisitos. Cada requisito ativo é cobrado por evidência — um AC ou NFR com teste
passando, uma regra ARCH executável ou um EVAL com critério estatístico — ou justificado
com `not_applicable` + motivo; "acho que cobre" não satisfaz. O `sdd profile` mostra a
matriz com o estado real de cada evidência. Detalhes e tabela completa em
[`docs/agentes.md`](docs/agentes.md).

## Comandos

| Comando | O que faz |
|---|---|
| `sdd init` | cria a estrutura (nunca sobrescreve) |
| `sdd enable <camada>` | liga design, tasks, constitution, arch, decisions, evals, mutate, strict, agentes |
| `sdd specify <nome>` | esqueleto de spec com IDs livres e as seções que o `--size` exige |
| `sdd validate` | analisa specs, tarefas, constituição, perfil: órfãos, ciclos, referências, critério vago |
| `sdd check` | roda testes, gates e regras de arquitetura; reprova critério sem teste passando |
| `sdd diff` | reprova código alterado sem a spec mudar junto (com exceções auditáveis) |
| `sdd mutate` | injeta falhas no código e reprova se os testes não as detectam |
| `sdd eval` | aplica critérios estatísticos a comportamento de LLM |
| `sdd arch` | verifica as regras de dependência entre camadas |
| `sdd profile` | mostra a matriz do perfil de agentes |

## O ciclo

| Etapa | Artefato | Verificado por |
|---|---|---|
| 0 Constituição | `constitution.yaml` | `validate`, `check` |
| 1 Especificação | `spec.yaml` | `specify`, `validate` |
| 2 Clarificação | `open_questions`, `assumptions` | pergunta aberta bloqueia o `validate` |
| 3 Plano | `design` | `validate` |
| 4 Tarefas | `tasks` | `validate`, `check` |
| 5 Análise | — | `validate` |
| 6 Implementação | código e testes | `check`, `diff`, `mutate`, `eval`, `arch` |

O `AGENTS.md` gerado ensina esse ciclo ao agente, com o que fazer e o que não fazer.

| Mudança | No commit |
|---|---|
| Comportamento mudou | spec alterada junto com o código |
| Bug (código descumpre spec correta) | `SDD-Fix: AC-012` + teste de regressão que cite o ID |
| Só a solução técnica mudou | `SDD-No-Spec-Change(nome-da-feature): <motivo>` |

## Documentação

- [Changelog](CHANGELOG.md): o que mudou em cada versão
- [Especificação](docs/especificacao.md): specs, rastreio, convenções por stack, size, premissas, tarefas
- [Verificação contínua](docs/verificacao.md): `diff`, `SDD-Fix`, `mutate`
- [Desenho arquitetural](docs/design.md): números, alternativas, riscos, modos de falha
- [Arquitetura e constituição](docs/arquitetura.md): `arch`, princípios executáveis
- [Comportamento de LLM](docs/evals.md): `eval`, intervalo de confiança, juiz LLM
- [Perfil de agentes](docs/agentes.md): matriz de módulos, requisitos críticos, LGPD
- [Configuração](docs/configuracao.md): todas as chaves e camadas
- [Limites, origem e créditos](docs/limites-e-creditos.md)

Este repositório verifica a si mesmo com oito specs: verificação, diff, mutação, evals,
arquitetura, governança, adoção e perfil de agentes. `sdd validate` mostra a contagem
atual de critérios; `sdd check` roda os testes, a constituição e as regras de arquitetura.

Os relatórios JSON e Markdown identificam a versão do kit, o formato e o comando.
Princípios dependentes de comandos separados ficam `PENDENTE` no check; uma regra
declarada não comprova execução. Veja [estados de evidência](docs/arquitetura.md).

## Licença

MIT. O perfil de agentes deriva da *SPEC-BASE v0.1* e o ciclo de sete etapas do *Guia SDD
para Agentes de IA*, ambos de Luciano Oliveira Nunes; detalhes em
[créditos](docs/limites-e-creditos.md#créditos).
