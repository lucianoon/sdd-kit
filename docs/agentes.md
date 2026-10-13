# Perfil de agentes

Catálogo de requisitos de referência para aplicações de agentes de IA, cobrados por evidência. Ligue com `sdd enable agentes` (ou `sdd init --profile agentes`).

## Perfil de agentes: `sdd init --profile agentes`

Para aplicações de agentes de IA, o kit traz um catálogo de requisitos de referência, a
[SPEC-BASE v0.1](limites-e-creditos.md#créditos) convertida em algo verificável. São 12 módulos e 61 requisitos
(`sdd profile --catalog`):

| Módulo | Ative quando |
|---|---|
| **N** Núcleo (obrigatório) | sempre: escopo, contratos, execução limitada, confiança, segredos... |
| **A** Identidade e isolamento | acesso restrito, dados privados, tenants |
| **T** Ferramentas e efeitos | o agente chama APIs, executa código ou altera estado |
| **R** Recuperação | RAG ou fontes fundamentam respostas |
| **M** Memória | contexto retido entre execuções |
| **H** Participação humana | revisão, aprovação ou transferência |
| **J** Tarefas longas | trabalho assíncrono ou retomável |
| **D** Delegação | multiagente ou subtarefas autônomas |
| **X** Arquivos e modalidades | imagem, áudio, vídeo, documentos |
| **C** Cache | reutilização de respostas |
| **P** Produção e escala | usuários reais, SLA (obrigatório no estágio `producao`) |
| **L** LGPD e PL 2338 | dados pessoais de titulares no Brasil |

O projeto declara em `specs/agents.yaml` o que se aplica e o que prova cada requisito:

```yaml
profile: agentes
stage: piloto              # local | piloto | producao
modules:
  N: ativo
  T: ativo
  R: {status: inativo, reason: sem base documental; respostas só de APIs}
  L: ativo
coverage:
  N-04: [AC-012, EVAL-002]          # IDs de AC, NFR, EVAL ou ARCH
  T-03: [AC-020]
  L-03: [AC-031, AC-032]
  L-06: {not_applicable: modelo hospedado no Brasil}
```

O `sdd validate` exige:

| Regra | Por quê |
|---|---|
| Módulo pendente: aviso em `local`, **erro** em `piloto`/`producao` | decisão adiada não pode ir para usuários reais |
| Módulo inativo exige motivo; o núcleo não pode ser desativado | "não se aplica" precisa ser uma decisão, não um esquecimento |
| Todo requisito de módulo ativo aponta para IDs existentes, ou `not_applicable` com motivo | requisito sem evidência é promessa |
| Requisito **crítico** (*) exige ao menos um AC, NFR ou ARCH e não aceita `not_applicable` | autorização, segredos, escrita duplicada e direitos do titular não se provam só por eval |
| `producao` exige o módulo P ativo | produção sem SLO, rollback e resiliência não é produção |
| Toda feature com `design` declara `design.limits` | N-03/N-07: nenhum agente roda sem deadline, etapas, chamadas e teto de custo |

O `sdd check` acrescenta ao relatório a matriz com o estado real de cada evidência
(`COBERTO`, `FALHA`, `N/A`), útil como trilha de auditoria em ambiente regulado. O módulo L
é referência técnica de engenharia, não parecer jurídico.

Também vieram da SPEC-BASE, e valem com ou sem o perfil:

- **Resultado desconhecido (T-04):** escrita não idempotente sem `status_query` exige
  `reconciliation` declarada; com consulta de status, o retry passa a ser permitido.
- **Evals críticos:** `critical: true` faz um único caso falho reprovar (`FALHA_CRITICA`),
  qualquer que seja a média. Para violações de autorização, por exemplo.
- **Efeitos proibidos:** `forbidden: [cobrar duas vezes]` no critério de aceitação; aparece
  no relatório junto do resultado esperado.
