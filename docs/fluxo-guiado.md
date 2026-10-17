# Análise e fluxo guiado

O sdd-kit separa a orientação do agente da verificação dos contratos. A análise é
estática; o guia entrega contexto para uma etapa. Testes, gates e evals continuam sendo
executados pelos comandos próprios.

## Analisar antes de implementar

```bash
sdd analyze
sdd analyze --json
sdd analyze -C /caminho/do/projeto
```

O comando reaproveita o mesmo carregador de `validate`, incluindo validação de schema,
referências, tarefas, constituição, perguntas abertas e critérios vagos. Mesmo se uma
spec estiver inválida, os diagnósticos aparecem e a matriz inclui as specs que puderam
ser carregadas. Uma matriz parcial não representa o projeto inteiro.

Os relatórios `.sdd/analyze.json` e `.sdd/analyze.md` identificam versão, comando e
alcance. `--json` mantém o stdout como um único documento JSON e também grava os dois
relatórios. Erros retornam código 1; somente avisos retornam 0. O comando não altera
specs ou código e não executa o comando de testes, gates ou harnesses.

Cada diagnóstico possui um ID derivado de seu conteúdo e fontes, repetível enquanto
esses dados não mudarem. Não é um identificador persistente após editar o diagnóstico.
Cenários iguais após normalizar caixa e espaços em given/when/then e forbidden geram
aviso, inclusive entre features; não há inferência de contradições ou duplicação semântica.

A matriz lista ACs, NFRs e EVALs com arquivo, origem e tarefas. Citar um REQ cobre seus
ACs, seguindo a regra existente de tarefas. `SEM_TAREFA` não é erro se a camada de tarefas
for opcional e não houver tarefas declaradas; quando há tarefas, critérios órfãos seguem
a validação existente. `DECLARADO` mostra vínculo, e `evidence_state: NÃO_EXECUTADA`
lembra que o analyze não rodou o teste. `status: done` não muda esse estado.

## Preparar uma etapa para o agente

Execute a partir da raiz do projeto, usando o valor de `feature` da spec:

```bash
sdd guide criar-pedido --stage clarify
sdd guide criar-pedido --stage plan
sdd guide criar-pedido --stage implement
sdd guide criar-pedido --stage converge
sdd guide criar-pedido --stage plan --json
```

O padrão é `clarify`. A saída contém instruções próprias da etapa, spec completa,
decisões referenciadas, constituição, arquitetura, perfil de agentes quando presente,
configuração e rastreabilidade. Specs vizinhas não entram como a selecionada; diagnósticos
e regras globais continuam visíveis para não ocultar conflitos no projeto. Conteúdo e
comandos da configuração são dados do projeto, não autorização de execução. Revise o
contexto antes de compartilhá-lo com um serviço externo.

| Etapa | Trabalho orientado |
|---|---|
| `clarify` | Priorizar lacunas relevantes, perguntar uma por vez até 5 e registrar respostas aceitas |
| `plan` | Elaborar design e tarefas com origem, dependências e critério de conclusão |
| `implement` | Implementar dentro do escopo, derivar testes dos critérios e executar verificação |
| `converge` | Inspecionar lacunas missing, partial, contradicts e unrequested; propor tarefas adicionais |

`guide` somente imprime o contexto: não lê relatórios antigos para declarar sucesso,
não escreve arquivos nem inicia agente, shell ou LLM. É necessário entregar o contexto
ao agente e executar o trabalho orientado. A saída Markdown e o JSON descrevem a mesma
etapa. Código 0 significa contexto disponível, nunca implementação aprovada.

Erros estáticos em qualquer parte do projeto produzem `BLOQUEADO` e código 1 para
`implement` e `converge`, ainda com contexto e diagnósticos. `clarify` e `plan` retornam
contexto para reparar as declarações existentes. Spec que não pôde ser carregada, nome
ambíguo, feature inexistente ou etapa desconhecida retornam código 2.

`ready_tasks` lista tarefas todo/doing cujas dependências estão declaradas como done;
se houver erros estáticos, a lista fica vazia. Essa lista não executa tarefas e não
comprova as evidências de suas dependências. Não há sugestão de paralelismo por arquivos
disjuntos: o schema atual não declara paths por tarefa.

## Convergência e aprovação

A revisão do agente pode identificar que um critério tem um teste inadequado, que um
caminho de erro ficou incompleto ou que houve trabalho fora do escopo. Isso é julgamento
semântico, não uma garantia do guia. Registre lacunas com referências e acrescente tarefas
sem renumerar ou apagar as existentes; preserve a intenção da spec.

Depois do trabalho, rode `sdd check` e, conforme aplicável, `sdd diff --base <ref-alvo>`,
`sdd mutate`, `sdd arch` e `sdd eval`. Cada resultado mantém seu alcance; uma etapa do
guia não muda os princípios constitucionais para APROVADO.

## Inspiração

O fluxo se inspira nas etapas de
[clarificação](https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md),
[análise](https://github.com/github/spec-kit/blob/main/templates/commands/analyze.md) e
[convergência](https://github.com/github/spec-kit/blob/main/templates/commands/converge.md)
do GitHub Spec Kit. A implementação é própria, com os contratos YAML do sdd-kit e
agregação determinística. Não importa os artefatos Markdown do Spec Kit nem fornece
compatibilidade automática com seus comandos ou extensões.

## Complementos locais

O contexto inclui `lessons.accepted` e `lessons.stale`, com referências e hashes.
Somente lições aceitas e atuais orientam o trabalho. Dados inválidos são recusados.
`integrate` instala entradas de agente que consomem este guia; `adequacy` registra
revisão semântica separada. Consulte [complementos](complementos.md).
