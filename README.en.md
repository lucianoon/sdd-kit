# sdd-kit

[Português](README.md) · English

[![ci](https://github.com/lucianoon/sdd-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/lucianoon/sdd-kit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sdd-kit-ai.svg)](https://pypi.org/project/sdd-kit-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Specification-Driven Development for AI-assisted work, with verification by
independent tools.**

The agent (Claude Code, Codex, Cursor, Copilot...) chooses **how** to implement. The spec
defines **what** is correct. `sdd` decides whether it is **ready**, running outside the LLM,
on your machine and in CI.

> LLMs propose and implement. Specifications define the contracts.
> Independent tools verify. Humans govern the highest-risk decisions.

sdd-kit combines agent guidance with executable verification: every criterion needs a
named passing test, code does not change unless the spec changes with it, weak tests are
exposed by mutation, and LLM behavior is measured with a statistical criterion. Code
checks use tools outside the agent. Evals with an LLM judge require an explicit policy
and are identified as probabilistic evidence.

## Installation

The command is `sdd`. The package name in `pyproject.toml` is `sdd-kit-ai`.

```bash
pipx install git+https://github.com/lucianoon/sdd-kit    # from source, always current
uv tool install git+https://github.com/lucianoon/sdd-kit # equivalent with uv
# pipx install sdd-kit-ai                                # from PyPI, when published
```

Python 3.10+. Works with any language whose test runner produces JUnit XML
(pytest, jest, vitest, Go, JUnit...); see [`examples/`](examples/).

## Start in 5 minutes

```bash
sdd init                                   # 4 files: config, sample spec, AGENTS.md, CI
sdd specify create-order --acs 2           # spec skeleton with unused IDs
# fill the fields marked PREENCHER:, write tests with the ID in the name
sdd validate && sdd check                  # ready = green
```

```
$ sdd specify create-order --acs 2
criado   specs/features/FEATURE-002/spec.yaml
IDs      REQ: REQ-002  AC: AC-002, AC-003
```

```python
def test_ac_002_order_persisted(): ...   # the criterion ID in the name links test and spec
```

```
$ sdd check
OK         AC-002   create-order: order is persisted
SEM_TESTE  AC-003   create-order: order is rejected
ERRO  AC-003 (create-order): SEM_TESTE

REPROVADO — report at .sdd/report.md
```

## Guided flow for the agent

After creating the spec, prepare feature context for the agent you use:

```bash
sdd guide create-order --stage clarify     # open questions and criteria to clarify
sdd guide create-order --stage plan        # design and traceable tasks
sdd analyze                               # diagnostics and criterion → task matrix
sdd guide create-order --stage implement   # context and declared task dependencies
sdd check
sdd guide create-order --stage converge    # instructions to review gaps after implementing
```

`guide` prints instructions and context; the agent works from them. It does not call an LLM,
change files, or run tests. `analyze` leaves sources untouched and writes static reports
to `.sdd/analyze.json` and `.md`, including when there are errors. Both accept `--json`.
Implementation and convergence are blocked by static errors; clarification and planning
remain available to fix the spec. See [guided flow](docs/fluxo-guiado.md) (Portuguese).

## Adopt incrementally

Start at the minimum and turn layers on when they make sense:

```bash
sdd init --preset minimo      # spec, check and diff (default)
sdd init --preset padrao      # + design, tasks, constitution, architecture, decisions
sdd init --preset completo    # + evals, mutation, strict criterion

sdd enable design tasks       # turn layers on in an existing project
sdd enable agentes            # AI-agent profile (61 requirements, including LGPD)
```

## AI agent applications

`sdd enable agentes` (or `sdd init --profile agentes`) brings a reference catalog of
requirements for agents, derived from *SPEC-BASE v0.1*: 12 modules (core, tools and
effects, retrieval, memory, human in the loop, delegation, production, LGPD/PL 2338...),
61 requirements. Every active requirement is charged against evidence — an AC or NFR with
a passing test, an executable ARCH rule, or an EVAL with a statistical criterion — or
justified with `not_applicable` plus a reason; "I think it covers it" does not satisfy.
`sdd profile` shows the matrix with the real state of each piece of evidence. Details and
the full table are in [`docs/agentes.md`](docs/agentes.md) (Portuguese).

## Complements for the flow

```bash
sdd integrate all                          # local entry points for Codex, Claude Code and Cursor
sdd adequacy template create-order         # separate review of test adequacy
sdd lesson list                            # proposed and accepted lessons
sdd change propose adjust-order --feature create-order --reason 'New rule'
sdd import-spec references/spec.md --format speckit --feature payments
```

Reviews use hashed references; currently accepted lessons are included in `guide`.
Proposals keep a baseline and history; archiving requires a fresh `check`. Spec Kit /
OpenSpec imports are drafts with provenance preserved and mandatory review.
See [complements and limits](docs/complementos.md) and the
[runnable demonstration of failure and fix](docs/demonstracao.md) (Portuguese).

## Risk-tiered review

```bash
sdd risk --base origin/main --author "$AUTHOR"   # change tier and required human approvals
sdd findings                                    # findings from an external LLM reviewer
sdd fixes --base v0.15.0                        # SDD-Fix corrections as evaluation cases
```

The floor comes from declared rules: globs per tier, `specs/`, and the severity of risks
on owning specs. An external classifier or LLM reviewer may **raise** the tier per file,
never lower it. LLM findings require an explicit policy, are probabilistic evidence, and
do not count as a human approval. See [risk-tiered review](docs/revisao.md) (Portuguese).

## Commands

| Command | What it does |
|---|---|
| `sdd init` | keeps existing starter files and applies the chosen preset layers |
| `sdd enable <layer>` | turns on design, tasks, constitution, arch, decisions, evals, mutate, strict, agentes |
| `sdd specify <name>` | spec skeleton with unused IDs and the sections required by `--size` |
| `sdd validate` | analyzes specs, tasks, constitution, profile: orphans, cycles, references, vague criteria |
| `sdd analyze` | consolidates errors, warnings, repeated scenarios and declared traceability matrix |
| `sdd guide <feature> --stage <stage>` | prepares context for clarify, plan, implement or converge |
| `sdd check` | runs tests, gates and architecture rules; fails a criterion without a passing test |
| `sdd diff` | fails changed code unless the spec changed with it (with auditable exceptions) |
| `sdd mutate` | injects faults into the code and fails if tests do not detect them |
| `sdd eval` | applies statistical criteria to LLM behavior |
| `sdd arch` | checks dependency rules between layers |
| `sdd profile` | shows the agent-profile matrix |
| `sdd risk` | computes the change-risk floor and the required human approvals |
| `sdd findings` | validates external LLM reviewer findings as probabilistic evidence |
| `sdd fixes` | exports `SDD-Fix` commits as cases for evaluating reviewers |

## The cycle

| Stage | Artifact | Verified by |
|---|---|---|
| 0 Constitution | `constitution.yaml` | `validate`, `check` |
| 1 Specification | `spec.yaml` | `specify`, `validate` |
| 2 Clarification | `open_questions`, `assumptions` | an open question blocks `validate` |
| 3 Plan | `design` | `validate` |
| 4 Tasks | `tasks` | `validate`, `check` |
| 5 Analysis | — | `validate` |
| 6 Implementation | code and tests | `check`, `diff`, `mutate`, `eval`, `arch` |

`guide --stage converge` guides an agent review after implementation, with traceable gaps
and extra tasks. That review does not replace the verification commands.

The generated `AGENTS.md` teaches this cycle to the agent, including what to do and what
not to do.

| Change | In the commit |
|---|---|
| Behavior changed | spec changed together with the code |
| Bug (code violates a correct spec) | `SDD-Fix: AC-012` + a regression test that cites the ID |
| Only the technical solution changed | `SDD-No-Spec-Change(feature-name): <reason>` |

## AI examples without growing the core

[`examples/rag`](examples/rag/) demonstrates authorized retrieval, cache invalidation,
fallback, budgets, traces, a reproducible manifesto and evaluation comparison using the
existing `check`, `eval` and gates. It is offline: it does not measure quality or latency
of an LLM. See also the [complexity assessment and simplicity rule](docs/simplicidade.md)
(Portuguese).

## Documentation

Most of the docs below are in Portuguese.

- [Changelog](CHANGELOG.md): what changed in each version
- [Specification](docs/especificacao.md): specs, tracing, per-stack conventions, size, assumptions, tasks
- [Continuous verification](docs/verificacao.md): `diff`, `SDD-Fix`, `mutate`
- [Guided flow](docs/fluxo-guiado.md): `analyze`, per-stage context and convergence limits
- [Architectural design](docs/design.md): numbers, alternatives, risks, failure modes
- [Architecture and constitution](docs/arquitetura.md): `arch`, executable principles
- [Internal architecture](docs/arquitetura-interna.md): modules, IO protection and distribution tests
- [October 2026 audit](docs/auditoria-2026-10.md): fixed finding, scope, validation and limits
- [LLM behavior](docs/evals.md): `eval`, confidence interval, LLM judge
- [Agent profile](docs/agentes.md): module matrix, critical requirements, LGPD
- [Risk-tiered review](docs/revisao.md): risk floor, LLM findings, fixes as eval
- [Configuration](docs/configuracao.md): every key and layer
- [Limits, origin and credits](docs/limites-e-creditos.md)

This repository checks itself with eleven specs: verification, diff, mutation, evals,
architecture, governance, adoption, agent profile, guided flow, artifacts and complements.
`sdd validate` shows the current criterion count; `sdd check` runs the tests, the
constitution and the architecture rules.

JSON and Markdown reports identify the kit version, the format and the command.
Principles that depend on separate commands stay `PENDENTE` in check; a declared rule
does not prove execution. See [evidence states](docs/arquitetura.md).

## License

MIT. The agent profile derives from *SPEC-BASE v0.1* and the seven-stage cycle from the
*Guia SDD para Agentes de IA*, both by Luciano Oliveira Nunes; details in
[credits](docs/limites-e-creditos.md#créditos).
