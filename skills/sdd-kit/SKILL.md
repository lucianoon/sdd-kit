---
name: sdd-kit
description: "Conduz features por Specification-Driven Development com o sdd-kit (CLI `sdd`): pergunta antes de presumir, registra a aprovação do usuário na spec e no plano, retoma o trabalho entre sessões e delega toda verificação a ferramentas fora do LLM (`sdd check`, `diff`, `mutate`, `eval`). Use ao especificar, planejar, implementar, validar ou retomar uma feature num projeto com specs/sdd.yaml, ou quando o usuário pedir SDD, spec-driven, especificar feature, aprovar spec ou retomar. Conducts spec-driven features with sdd-kit: specify, plan, implement, verify, resume."
license: MIT
metadata:
  author: Luciano Oliveira Nunes - github.com/lucianoon
---

# sdd-kit

Você conduz a conversa; o `sdd` decide o que está pronto. A spec define **o que** é correto,
você escolhe **como** implementar, e nenhuma decisão vive só na conversa: o que importa fica
no repositório.

## Antes de tudo

- Confira `sdd --version`. Sem o CLI, peça ao usuário para instalar (`pipx install sdd-kit-ai`)
  e pare; nunca simule a saída de um comando.
- Projeto sem `specs/sdd.yaml`: proponha `sdd init --preset padrao` (liga design, tarefas,
  constituição, arquitetura, decisões e aprovação) e espere o sim.
- Leia o `AGENTS.md` do projeto. Ele vence esta skill quando os dois divergirem.

## Contrato (vale mesmo sem ler o resto)

1. **Pergunte, não presuma.** Lacuna que muda comportamento ou teste vai para
   `open_questions`, uma pergunta por vez. Padrão escolhido por você vira `assumptions`, com
   justificativa. Pergunta sem resposta bloqueia o `sdd validate`, e isso é proposital.
2. **Duas paradas para o usuário: a spec e o plano.** Apresente a etapa, pergunte e registre
   a resposta com as palavras dele:
   `sdd approve <feature> --stage spec --by "<nome>" --quote "<palavras do usuário>"`.
   **Nunca registre aprovação que o usuário não deu.** Um "pode seguir" anterior a ver a
   etapa não aprova a etapa. Mudou o conteúdo depois? A aprovação fica desatualizada; peça
   de novo.
3. **Testes vêm dos critérios**, com o ID no nome (`test_ac_012_...`, `it("AC-012 ...")`), e
   verificam o resultado e os efeitos proibidos da spec, nunca a sua implementação.
4. **Pronto é decidido pelo `sdd check`**, não pela conversa. Rode e mostre a saída.
   `sdd diff`, `sdd mutate`, `sdd eval` e `sdd arch` têm alcance próprio: rode quando
   aplicáveis e diga o que não foi executado. Nunca enfraqueça, pule ou apague um teste ou um
   critério para passar.
5. **Aprovar a spec e o plano autoriza só trabalho local.** Commit, push, deploy, migração e
   banco de produção pedem autorização para aquela ação.

## Fluxo

O `size` da spec define a profundidade; não faça cerimônia que a feature não pede.

| size | spec | plano (design e tarefas) | aprovação |
|---|---|---|---|
| small | critérios diretos | dispensado | conforme `approval_required_for` |
| medium | completa | tarefas quando houver mais de 3 passos | spec e plano |
| large, complex | completa, perguntas antes | design e tarefas obrigatórios | spec e plano |

### Nova feature

1. `sdd specify <nome> --size <size> --acs <n>`. Se a feature toca persistência,
   autenticação, pagamentos, chamadas externas, concorrência ou transições de estado, inclua
   `--touches <dimensões>`: as perguntas do catálogo entram em `open_questions`.
2. `sdd guide <feature> --stage clarify`: faça as perguntas ao usuário, registre as
   respostas, troque cada `PREENCHER:` por conteúdo real. `sdd validate` até ficar verde,
   exceto pelo que o plano ainda vai preencher.
3. Apresente a spec. Com o sim do usuário: `sdd approve <feature> --stage spec ...`.
4. `sdd guide <feature> --stage plan`: design (números com fonte, nunca inventados;
   alternativas; riscos; dependências com timeout, retry e fallback) e tarefas pequenas com
   `origin`, `depends_on` e `done_when`. `sdd validate` e `sdd analyze`.
5. Apresente o plano. Com o sim do usuário: `sdd approve <feature> --stage plan ...`.
6. `sdd guide <feature> --stage implement`. Se vier BLOQUEADO, resolva os bloqueios
   listados antes de tocar no código. Para cada tarefa iniciável: testes dos critérios,
   código, `sdd check`, e só então `status: done` com `evidence`.
7. `sdd guide <feature> --stage converge`: revise lacunas contra a spec e rode as
   verificações aplicáveis (`sdd diff --base <ref>`, `sdd mutate`).

### Retomar (sessão nova ou depois de compactação)

`sdd guide <feature> --stage resume` mostra aprovações, perguntas sem resposta, tarefas por
status e o próximo passo calculado. Reconcilie com `git status` e `git log`: se divergirem,
vale o repositório. Em sessão nova, proponha o próximo passo ao usuário antes de escrever
código.

### Mudanças depois de pronto

| Situação | O que fazer | No commit |
|---|---|---|
| Comportamento mudou | spec alterada junto com o código | — |
| Bug (código descumpre spec correta) | correção e teste de regressão com o ID | `SDD-Fix: AC-NNN` |
| Só a solução técnica mudou | comportamento preservado | `SDD-No-Spec-Change(<feature>): <motivo>` |

## Saída

Faça o trabalho em vez de narrar a etapa. Escreva specs, decisões e resumos em voz direta:
o veredito primeiro, sem rodeio. Fato você procura (código, docs, specs); decisão você
pergunta. "Não encontrei documentação para isso" vale mais que uma resposta plausível
inventada.
