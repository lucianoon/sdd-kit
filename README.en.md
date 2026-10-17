# sdd-kit

[Português](README.md) · English

**Spec-driven development with executable evidence outside the coding agent.**

Your agent chooses how to implement. Specifications define the contracts. Independent
tools check the configured evidence locally and in CI; people govern semantic and
high-risk decisions.

## Start

```bash
pipx install sdd-kit-ai
sdd init
sdd specify create-order --acs 2
# Fill the generated specification and write tests with AC IDs in their names.
sdd validate
sdd check
sdd integrate all   # optional local entry points for Codex, Claude Code and Cursor
```

Python 3.10+. Test runners must produce JUnit XML. Working examples cover pytest,
Jest, Vitest and Go. Install from Git for features not yet released to PyPI:

```bash
pipx install git+https://github.com/lucianoon/sdd-kit
```

## What it checks

| Command | Evidence |
|---|---|
| `validate`, `analyze` | Schema, references, scope and declared traceability |
| `guide` | Stage context for your agent; no model execution |
| `check` | Fresh tests, criterion IDs, gates and architecture rules |
| `diff` | Code/spec changes with explicit, auditable exceptions |
| `mutate` | Whether tests detect generated faults |
| `eval` | LLM evaluation results and configured statistical thresholds |
| `adequacy` | Integrity and freshness of a separate semantic test review |
| `lesson` | Proposed and explicitly accepted local lessons |
| `change` | Propose, inspect, apply and archive changes to an existing spec |
| `import-spec` | Conservative Spec Kit/OpenSpec Markdown drafts with provenance |

Choose `minimo`, `padrao` or `completo` presets and enable layers incrementally.
The verifier uses commands and JUnit instead of model SDKs. Agent instructions and
semantic reviews remain distinct from executed evidence.

A passing named test does not prove it tests the intended requirement. Mutation is
lexical, architecture checks have language-specific limits, and eval quality depends
on representative datasets. See [limits](docs/limites-e-creditos.md) and the
[complement guide](docs/complementos.md), currently in Portuguese.

## See it fail, then pass

Follow the [runnable pytest demonstration](docs/demonstracao.md). The repository
also checks its own specifications and includes package-installation smoke tests.

## References and license

MIT. Original implementation with ideas credited to GitHub Spec Kit, OpenSpec,
TLC Spec-Driven and the author's SDD guide and agent requirements catalog.
See [credits](docs/limites-e-creditos.md).
