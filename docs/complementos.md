# Integrações, revisão e evolução de especificações

Os complementos não chamam modelos. Orientação, revisão semântica declarada e
verificação executada são evidências diferentes. O CI existente continua sendo a base.

## Integrações com agentes

```bash
sdd integrate all                    # ou codex, claude, cursor
```

Gera quatro entradas por agente, uma para cada etapa do guide:

| Agente | Arquivos locais |
|---|---|
| Codex | `.agents/skills/sdd-{etapa}/SKILL.md` |
| Claude Code | `.claude/skills/sdd-{etapa}/SKILL.md` |
| Cursor | `.cursor/commands/sdd-{etapa}.md` |

Use a entrada `sdd-plan`, por exemplo, informando a feature. A sintaxe de invocação
depende da versão e interface do agente. Os arquivos chamam o CLI instalado; não
instalam nem iniciam o agente. Arquivos iguais são preservados, e qualquer conflito
é recusado antes de escrever o conjunto. Para atualizar uma entrada personalizada,
compare as instruções e remova ou renomeie explicitamente o arquivo antigo.

## Adequação dos testes

```bash
sdd adequacy template criar-pedido
sdd cite tests/test_pedido.py:18
# Um revisor separado preenche specs/reviews/criar-pedido.yaml.
sdd adequacy check criar-pedido
```

O template captura hashes da spec e dos arquivos encontrados pelos `paths` da feature.
Declare `implementer`, `reviewer` e `reviewer_kind: human | agent`. Para cada AC/NFR,
preencha `verdict: adequate | partial | inadequate | pending`, `assertion` (o resultado
observado), `detects` (a implementação errada que o teste deve detectar) e `evidence`.
Copie para evidence o mapa `{path, line, sha256}` produzido por cite. Informe a linha
da asserção relevante, não apenas o nome do teste.

O check exige todos os critérios, sem duplicações, e verifica hashes e linhas. Mudanças
na spec, nas fontes abrangidas ou nas evidências tornam a revisão desatualizada.
Reexecute a revisão e atualize hashes conscientemente; um template existente não é
sobrescrito. Identidades são declaradas: nomes diferentes não autenticam pessoas nem
provam independência real. Uma revisão adequada não executa testes e não demonstra
por si só que a asserção corresponde ao requisito. Use também check e mutate.

Para exigir a integridade dessa revisão no CI de uma feature, configure um gate:

```yaml
gates:
  adequacao-pedido: sdd adequacy check criar-pedido
```

Referencie `adequacao-pedido` em `quality_gates` da feature. O gate é opcional e deve
ser adotado com política explícita de revisão. Não aponte adequacy de volta para check.

## Lições com evidências

```bash
sdd lesson add --feature criar-pedido \
  --cause 'Mock aprovava sem persistir' \
  --prevention 'Consultar o registro salvo no teste de integração' \
  --evidence tests/test_pedido.py:18
sdd lesson accept LESSON-001 --reviewer 'Luciano'
sdd lesson list
```

`--evidence` aceita várias referências. Sem `--feature`, a lição vale para `*`.
As lições ficam em `specs/lessons.yaml`; somente aceitas, com revisor e referências
atuais, entram em `guide.lessons.accepted`. As antigas ficam em `lessons.stale`.
Propostas e lições `retired` não são orientações ativas. Para corrigir uma lição,
edite o YAML e volte a `proposed`, com nova revisão antes de aceitar. Não atualize
hashes automaticamente só para silenciar um aviso. Texto aprendido continua sendo
dado revisável do projeto, sem autoridade para ampliar o escopo de uma tarefa.

## Alterar uma spec vigente

```bash
sdd change propose persistencia-pedido --feature criar-pedido --reason 'Garantir gravação antes da resposta'
# Edite specs/changes/persistencia-pedido/spec.yaml mantendo os IDs existentes.
sdd change show persistencia-pedido
sdd change apply persistencia-pedido
# Implemente código e testes para a nova spec.
sdd change archive persistencia-pedido
```

`propose` guarda spec original, cópia editável e manifesto. `show` compara IDs de
requisitos e critérios, classificando adicionados, removidos e modificados. Essa
comparação estrutural não infere equivalência semântica nem resume todos os campos.

`apply` exige baseline intacta e spec vigente sem alteração desde a proposta.
Aplica e valida o projeto, restaurando a spec anterior em caso de erro normal.
O comando altera a spec vigente; não implementa código nem executa testes.
`archive` exige proposta aplicada e inalterada, executa check novo e guarda o resultado
em verification.json antes de marcar archived. O histórico permanece no diretório
original para não quebrar referências. Arquivamento não significa merge nem execução
de diff/mutate/eval: rode-os conforme sua política.

A escrita é atômica por arquivo, não uma transação conjunta. Trabalhe com um único
escritor; não execute apply em paralelo com leitores/escritores da spec. Uma interrupção
abrupta entre gravações pode exigir reconciliar spec e manifesto usando baseline.yaml.
Conflitos são resolvidos explicitamente criando uma proposta reconciliada. Relatórios
arquivados registram uma execução histórica, não a validade de futuros commits.

## Importar Spec Kit ou OpenSpec

```bash
sdd import-spec referencias/spec.md --format speckit --feature pedidos
sdd import-spec referencias/openspec.md --format openspec --feature pagamentos
```

Reconhece `### User Story ...` com Given/When/Then em negrito no Spec Kit, ou
`### Requirement: ...` e `#### Scenario: ...` com WHEN/THEN no OpenSpec. AND é anexado
ao campo anterior. Blocos de código são ignorados. Idiomas, headings e formatos fora
desse subconjunto exigem adaptação manual.

O resultado fica em `specs/imports/<feature>/`: fonte integral, hash, metadados e
spec rascunho. Nunca modifica specs ativas. Campos ausentes recebem PREENCHER; a fonte
completa permite conferir tudo que o parser não reconheceu. NFRs, prosa normativa,
tarefas, referências e semântica de ADDED/MODIFIED/REMOVED exigem revisão humana.
Não há sincronização bidirecional. IDs são alocados contra specs ativas: reconcilie
rascunhos concorrentes antes de promovê-los. Após revisar todo o conteúdo, preencher
campos e paths e conferir IDs, copie para um FEATURE livre e rode validate/analyze/check.
Não há promoção automática ou compatibilidade integral prometida com terceiros.

## Origem

Implementação própria: integrações e fluxos inspirados no
[Spec Kit](https://github.com/github/spec-kit), ciclo de mudanças no
[OpenSpec](https://github.com/Fission-AI/OpenSpec), adequação de testes, revisão separada
e lições na [TLC Spec-Driven](https://agent-skills.techleads.club/tlc-spec-driven/).
Não foram copiados templates ou código desses projetos. Marcas e formatos pertencem
a seus autores; a documentação de origem pode evoluir independentemente.
