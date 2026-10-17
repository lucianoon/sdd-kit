# Limites, origem e créditos

O que o kit não garante, de onde vieram as ideias e o que vem depois.

## Agnosticismo

- **De agente:** as instruções ficam em `AGENTS.md`. Se a sua ferramenta lê outro arquivo
  (ex.: `CLAUDE.md`), aponte-o para o `AGENTS.md` em vez de duplicar regras.
- **De linguagem:** o motor só conhece comandos de shell e JUnit XML.

## Limites conhecidos

- O rastreio prova que existe um teste **nomeado** para o AC e que ele passa. O `mutate`
  prova que os testes da feature detectam código errado, mas não que o teste do AC-001
  verifica exatamente o `then` do AC-001. Isso continua sendo revisão humana.
- A mutação é textual, com regras léxicas por extensão: pode gerar mutantes equivalentes
  (sobrevivem sem culpa dos testes) e não remove linhas arbitrárias nem troca chamadas ou
  strings. Generics e JSX são reconhecidos por heurística de uma linha: tag JSX quebrada em
  várias linhas ou `f(a<b, c>d)` (ambíguo também para o compilador de C#) podem gerar mutante
  que não compila; fora de Python, só `mutation.build` separa esse caso de um mutante morto.
  Execução interrompida
  à força (kill) pode deixar a cópia em `/tmp/sdd-mutate-*`; o próximo `mutate` remove as
  órfãs mais velhas que 24 horas.
- `size` é declarado por quem escreve a spec; a única trava objetiva é o número de arquivos.
- O `arch` usa AST no Python e texto nas outras stacks: não vê dependências indiretas (A importa B que importa
  infra), import dinâmico por string montada em tempo de execução, nem injeção por
  reflexão. Cobre o caso comum; para o resto, ferramentas dedicadas como gates.
- `dependencies` garante que o modo de falha foi **declarado e tem teste ligado**, não que
  o teste simula a falha de verdade. Revisão humana confere.
- O `eval` garante a aritmética e a integridade dos resultados, não a **qualidade do
  dataset**: um dataset fácil demais ou que não representa produção aprova um agente ruim.
  Também não impede um harness que grava `pass: true` sem chamar o modelo; isso é código
  revisável no PR, como qualquer teste.
- Evals no CI medem antes do merge. Deriva do modelo e comportamento em produção pedem
  observabilidade e evals contínuos sobre tráfego real, fora do escopo do kit.
- `invariants` e `out_of_scope` são documentados, não verificados.
- A seção `design` garante que a análise **existe e tem estrutura**, não que é **boa**:
  duas alternativas de fachada passam no validador, e `source` não prova que o número é real.
- Um NFR testado no CI aproxima, mas não substitui, medição em produção (SLO/observabilidade).
  Números sem `id` orientam o desenho mas não são verificados.
- O `diff` detecta divergência **por mudança** (código mexeu, spec não), não por conteúdo:
  edição semântica na spec (valores ou estrutura) satisfaz a regra; comentário, espaço e
  reordenação de chaves não contam. O revisor ainda confere se a edição descreve a mudança.
  O trailer de exceção é limitado à feature nomeada; ainda vale para o intervalo inteiro
  daquela feature. O formato global exige opt-in de migração e emite aviso.
- Sem orçamento de autonomia executável (hoje é texto na constituição). O `guide`
  prepara contexto por etapa, mas não inicia agente, gera respostas ou executa o plano.

## O que veio da TLC Spec-Driven

Ideias da [TLC Spec-Driven](https://agent-skills.techleads.club/tlc-spec-driven/)
(Felipe Rodrigues, Tech Leads Club), reimplementadas como verificação determinística:

| Ideia na TLC | Como ficou aqui |
|---|---|
| Profundidade ajustada à complexidade | `size` + `design_required_for` + trava no `diff` |
| Requirement closure gate | `open_questions` sem resposta bloqueiam o `validate` |
| Tabela de premissas | `assumptions` com padrão escolhido e justificativa obrigatórios |
| Decisões de projeto (AD-NNN) | `specs/decisions.yaml`, referências validadas |
| Discrimination sensor (LLM injeta falhas) | `sdd mutate`, mutação determinística |
| Fluxo por fases, testes derivados da spec, blast radius | `AGENTS.md` e constituição gerados |

**Não trouxemos:** um verificador LLM como aprovador de ACs e NFRs (evals com juiz LLM
têm política própria, AD-004/AD-005), a orquestração automática de sub-agentes (é processo do agente, não verificação).
A camada de lições revisadas e o registro de adequação foram acrescentados como
complementos explícitos; veja [o guia](complementos.md).

## Próximos passos sugeridos

1. Orçamento de autonomia executável: caminhos protegidos que exigem aprovação (CODEOWNERS).
2. Contratos: validar OpenAPI/JSON Schema contra a implementação como gate nativo.
3. Associar exceções a arquivos ou commits específicos dentro da feature; hoje o alcance
   é o intervalo da feature nomeada.

Este repositório se verifica: `sdd check` na raiz roda as onze specs de capacidades em
`specs/features/FEATURE-*/spec.yaml`.

## Créditos

Análise com rastreabilidade e orientação por etapas de clarificação, plano, implementação
e convergência foram inspiradas pelo [GitHub Spec Kit](https://github.com/github/spec-kit).
O sdd-kit implementa seu próprio analisador estático e gerador de contexto, sem copiar
templates nem adotar o agente como aprovador dos contratos; veja [fluxo guiado](fluxo-guiado.md).

O ciclo de sete etapas, as tarefas rastreáveis, a constituição com IDs e o tratamento de
mudanças vêm do *Guia SDD para Agentes de IA* (Luciano Oliveira Nunes), baseado no vídeo
"Este é o futuro do desenvolvimento de software", do canal Balta.

O perfil de agentes é derivado da *SPEC-BASE v0.1 — Aplicações de agentes de IA*
(Luciano Oliveira Nunes, 13/10/2026), condensada e acrescida do módulo L (LGPD/PL 2338).

Integrações locais inspiradas no Spec Kit e OpenSpec; ciclo de propostas inspirado no
[OpenSpec](https://github.com/Fission-AI/OpenSpec); adequação e lições inspiradas na TLC.
Implementação própria, sem copiar código ou templates dos projetos citados.
