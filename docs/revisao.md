# Revisão escalonada por risco

Quando agentes escrevem a maior parte do código, ler cada linha deixa de ser possível, e
a pergunta muda de "um humano leu?" para "o que pode dar errado nesta mudança, e qual
verificação pega isso?". O sdd-kit responde à parte que dá para decidir sem modelo e
deixa a parte probabilística para ferramentas externas, com uma regra de assimetria
(AD-007):

- o **piso** de rigor vem de regras declaradas e é reproduzível;
- classificadores e revisores LLM externos **só elevam** o rigor, nunca reduzem;
- aprovação de agente **nunca conta** como aprovação humana.

O desenho segue o processo publicado pelo time do Claude Code
([How the Claude Code team does code review](https://claude.dev/blog/solving-code-review-at-anthropic/),
out/2026), adaptado ao princípio do kit de verificar fora do LLM.

## `sdd risk`: piso de risco e aprovações

```bash
sdd risk --base origin/main                                 # informativo, código 0
sdd risk --base origin/main --author lucianoon --approvals 1 # reprova (1) se faltar aprovação
sdd risk --base origin/main --json
```

Para cada arquivo alterado desde o merge-base, o tier é o maior entre:

| Fonte | Regra |
|---|---|
| `review.tiers` | maior tier cujo glob casa; sem casamento, `review.default_tier` |
| `specs/` | mínimo `medium`: mudar o contrato é decisão humana |
| `specs/sdd.yaml` | sempre `high`: define os gates e o próprio piso |
| spec dona | a maior severidade em `design.risks` da feature cujos `paths` casam o arquivo |

O tier da mudança é o maior entre os arquivos (`.sdd/` fica de fora: são relatórios e
entradas do kit). `review.approvals` traduz o tier em aprovações humanas (padrão 0, 1
e 2). Com `review.trusted_authors` preenchido, autor fora da lista exige ao menos 1.

`--approvals` recebe só aprovações **de pessoas**, contadas pelo CI na forja. O kit não
consulta a API da forja nem autentica quem aprovou. Sem `--approvals`, o resultado é
informativo e o comando sai com 0, o que permite usá-lo só para publicar o tier no
resumo do PR, como faz o CI deste repositório.

### Escalações externas

Um classificador que lê o diff enxerga risco semântico que um glob não vê, como uma
mudança de autorização num arquivo "inofensivo". Ele grava `review.escalations`:

```json
{"version": 1, "escalations": [
  {"tier": "high", "reason": "altera checagem de permissão", "source": "loopway/classifier"}
]}
```

Escalação acima do tier atual eleva e fica registrada no relatório. Igual ou abaixo é
ignorada com motivo. Arquivo inválido sai com código 2: entrada malformada nunca é
lida como "sem escalação".

## `sdd findings`: achados de revisor LLM

O revisor (vários agentes caçando bugs, verificadores votando) roda fora do kit. O
harness grava `review.findings`:

```json
{"version": 1, "reviewer": "loopway/claude-opus", "round": 1,
 "reviewed": {"src/pedido.py": "<sha256 do arquivo revisado>"},
 "findings": [
   {"id": "F-7a1c", "severity": "important", "path": "src/pedido.py", "line": 42,
    "category": "validação ausente", "message": "total negativo aceito",
    "votes": 3, "voters": 3, "round": 1, "status": "open"}
 ]}
```

O kit exige `review.allow_llm_findings: true`, marca a evidência como probabilística e
reprova quando:

- há achado `important` aberto com maioria de votos (`votes` maior que metade de `voters`);
- algum arquivo de `reviewed` mudou depois da revisão: a revisão vale para aquele conteúdo;
- um ID se repete, ou a mesma mensagem no mesmo arquivo reaparece com outro ID;
- `round` passa de `review.max_rounds`: em vez de mais uma rodada, reveja a abordagem.

`nit`, `pre_existing` (o bug já existia antes da mudança) e achados sem consenso não
bloqueiam. Todo achado precisa de destino: `fixed` ou `dismissed` com `disposition`
(`wrong`, `intentional` ou `irrelevant`) e `reason`. O resumo conta os destinos. A
fração de `wrong` é a medida de ruído do revisor: comentário que leva a mudança
desnecessária custa mais quando quem corrige é outro agente.

## Convergência

Um autor agente e um revisor agente podem se ocupar indefinidamente. O
`sdd guide <feature> --stage converge` instrui o agente a não repetir lacunas de
rodadas anteriores, separar o introduzido do pre-existente, apontar a classe do
problema, revisar só o diff novo depois da primeira rodada e parar em
`review.max_rounds`.

## Adequação com revisor humano

`sdd adequacy check` reprova revisão com `reviewer_kind: agent` quando a feature tem
risco `high` na spec ou está em `review.human_adequacy`. Identidade continua declarada,
não autenticada; o relatório diz se a evidência é humana declarada ou probabilística.

## `sdd fixes`: correções como casos de avaliação

```bash
sdd fixes --base v0.15.0 > casos.json
```

Lista os commits com `SDD-Fix: AC-NNN`, com critérios, features donas, arquivos e
testes do commit. Cada caso é um bug real que escapou: dá para perguntar se o revisor
o pegaria na mudança original e reavaliar o revisor sempre que prompt, ferramentas ou
modelo mudarem. Um caso não comprova detecção, e clone raso pode omitir commits
(`git fetch --depth=1000` antes).

## Limites

- O piso por glob e risco declarado não infere nada: o que não está declarado não eleva.
- A contagem de aprovações é a que o CI informa; o kit não verifica identidades.
- Votação, deduplicação semântica fina e o classificador ficam no harness externo.
- Achados e escalações são entradas; a qualidade do revisor depende de quem o avalia.
