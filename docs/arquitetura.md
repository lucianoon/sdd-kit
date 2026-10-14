# Arquitetura e constituição

Regras de dependência entre camadas (`sdd arch`) e princípios do projeto com cobrança explícita.

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

## Constituição executável: `specs/constitution.yaml`

```yaml
principles:
  - id: CONST-01
    rule: A aplicação verifica autorização fora do modelo de linguagem.
    enforced_by: [ARCH-001, AC-014]         # ARCH, AC/NFR/EVAL, gate:<nome>, kit:<recurso>, profile:<req>
  - id: CONST-02
    rule: Segredos não aparecem no código.
    enforced_by: [gate:segredos]            # o gate roda no check mesmo que nenhuma spec o peça
  - id: CONST-03
    rule: Novas dependências exigem justificativa registrada.
    manual: decisão em decisions.yaml revisada no PR
```

Todo princípio precisa de cobrança ou de procedimento manual. O estado descreve a
evidência desta execução:

| Estado | Significado |
|---|---|
| `DECLARADO` | referência válida, sem contexto de execução |
| `PENDENTE` | verificação aplicável que este comando não executou, ou mutação de alcance parcial |
| `APROVADO` | todas as evidências automáticas associadas passaram neste alcance |
| `VIOLADO` | alguma evidência associada falhou |
| `NÃO_APLICÁVEL` | o projeto não declara objeto para a verificação |
| `MANUAL` | existe revisão humana ainda necessária |

O `check` executa testes, gates e arquitetura. `kit:diff`, `kit:mutate` e `kit:eval`
aplicáveis ficam pendentes; o comando correspondente reporta sua própria execução.
Relatórios antigos não são usados para transformar pendência em aprovação.
`kit:design`, `kit:tasks`, `kit:dependencies` e `kit:limits` indicam validação estrutural
do conteúdo declarado; continuam sujeitos aos [limites semânticos](limites-e-creditos.md).
O resultado geral de cada comando se limita ao alcance que ele verifica. Os IDs são `CONST-NN` (e não `C-NN`) para não colidir
com o módulo Cache do perfil de agentes.
