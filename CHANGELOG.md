# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
[SemVer](https://semver.org/lang/pt-BR/). Versão 0.x: minor pode mudar comportamento
observável; mudanças que quebram projetos que adotam o kit explicam a migração.

## [Não publicado]

## [0.15.0] — 2026-10-22

### Adicionado

- Cobertura no CI (`pytest-cov`) com relatório no resumo do job; badges de CI, PyPI
  (`sdd-kit-ai`) e licença MIT nos READMEs.
- Job de CI com as versões mínimas das dependências de runtime, no Python 3.10.
- GitHub Release automático ao publicar por tag `v*`, com notas extraídas da seção
  correspondente do `CHANGELOG.md`.

- Revisão escalonada por risco (FEATURE-012, AD-007). `sdd risk` calcula o tier da
  mudança por regras declaradas (`review.tiers`, mínimo medium em `specs/`, high em
  `specs/sdd.yaml`, severidade dos riscos da spec dona) e as aprovações humanas exigidas;
  escalações externas só elevam o tier. `sdd findings` valida achados de revisor LLM
  externo como evidência probabilística: bloqueia `important` aberto com consenso,
  revisão desatualizada, achado repetido e rodada acima de `review.max_rounds`, e conta
  destinos para medir ruído. `sdd fixes` exporta commits `SDD-Fix` como casos para
  avaliar revisores. Nova seção `review` em `specs/sdd.yaml`; padrões não mudam nada em
  projetos existentes.
- `sdd adequacy` exige `reviewer_kind: human` em features com risco high ou listadas em
  `review.human_adequacy` (AC-131). **Migração:** revisões de agente nessas features
  passam a reprovar; registre um revisor humano.
- `sdd guide --stage converge` orienta a convergência: sem repetir lacunas, separando o
  pre-existente, apontando a classe do problema e parando em `review.max_rounds` (AC-132).

- Exemplo RAG offline com isolamento, cache, fallback, orçamentos e traces; avaliação
  reproduzível com manifesto e comparação pareada, usando comandos e gates existentes.
- Avaliação de complexidade e critérios de simplicidade; nenhum comando público,
  schema central ou dependência de runtime acrescentado nesta entrega.

- Versão de desenvolvimento 0.15.0: entradas locais para Codex, Claude Code e Cursor,
  preservando personalizações; revisões de adequação com hashes e evidências;
  lições propostas/aceitas com contexto por feature e detecção de referências antigas.
- Ciclo de propostas com baseline, aplicação validada e arquivamento com check novo.
- Importação conservadora de cenários Spec Kit/OpenSpec, com fonte e limites explícitos.
- README em inglês e demonstração executável de regressão e correção.

- `sdd mutate` com operadores ampliados (REQ-033): `*`↔`/`, `%`→`*`, constante inteira
  `n`→`n+1`, remoção de `not` e `!`, `is`↔`is not`, `in`↔`not in` e `return <expr>` →
  `return None`/`undefined`. **Migração:** os novos mutantes podem baixar o score de projetos
  existentes; fortaleça os testes (ou marque equivalentes com `sdd: no-mutate`), não reduza o
  `min_score`.
- `mutation.build`: comando de compilação por mutante; falha marca o mutante como inválido,
  fora do score e listado no relatório. Em Python, mutante com erro de sintaxe é descartado
  antes de rodar testes.

- Workflow de release por tag (`v*`): build + `twine check` + publicação no PyPI
  via trusted publishing (sem segredo no repo). Requer configurar o *pending publisher*
  uma vez no PyPI: projeto `sdd-kit-ai`, repo `lucianoon/sdd-kit`, workflow `release.yml`.
- Exemplo `examples/multi/`: duas specs independentes (`pedidos`, `fretes`) com código
  realmente acoplado (o frete literalmente importa o limite VIP dos pedidos), paths
  próprios por feature e IDs únicos entre specs — exercita a regra de dono por feature.
- README com seção dedicada às aplicações de agentes de IA (12 módulos, 61 requisitos,
  LGPD/PL 2338) e à instalação pelo PyPI.

### Modificado

- Versão de fonte única: `__version__` lê `importlib.metadata.version("sdd-kit-ai")`;
  o número 0.15.0 fica só no `pyproject.toml`. AC-113 passa a exigir essa fonte única
  e o GitHub Release com notas do CHANGELOG.
- Dependências de runtime com teto: `typer>=0.16,<1` (0.12.0 é meta-pacote;
  0.12–0.15 quebram com Click 8.2+), `pydantic<3`, `pyyaml<7`.
- `README.en.md` alinhado ao conteúdo do README em português.
- Workflow `ci` não esconde mais falhas com `|| true` / `2>/dev/null`; relatórios
  ausentes emitem `::warning::` explícito.

- O workflow gerado por `sdd init` usa `actions/checkout@v7` e `actions/setup-python@v7`,
  as mesmas versões do CI do kit.
- Nome do pacote no PyPI: `sdd-kit` → **`sdd-kit-ai`** — o nome antigo está ocupado no
  PyPI por outro projeto (VS Code/Copilot). O comando `sdd`, o módulo `sdd` e a
  instalação pela fonte continuam iguais.

### Corrigido

- README apresentava `pipx install sdd-kit-ai` como instalação atual do PyPI, mas o
  pacote ainda não existe lá. A instalação documentada passa a ser pela fonte
  (`pipx`/`uv`); o comando do PyPI fica só como previsão.
- `sdd mutate` tratava `//` como comentário em Python (divisão inteira escondia o resto da
  linha da mutação) e `#` como comentário em JS/TS (campos privados).
- `<` e `>` de tipos genéricos e tags JSX viravam mutantes que só quebravam a compilação e
  contavam como mortos, inflando o score.
- `+` e `-` grudados num identificador terminado em `e` (`size+1`) não eram mutados; só a
  notação científica (`1e-5`) deve ficar de fora.
- Suíte sem mutações que estoura `mutation.timeout` era relatada como "a suíte não passa";
  agora o erro cita o timeout (AC-120).
- Exemplo jest: override do `js-yaml` 4 em `@istanbuljs/load-nyc-config` tira da árvore o
  `sprintf-js` (GHSA-hp3w-g68c-fv3c, sem versão corrigida publicada).
- `pip` declarado nos extras `dev`: o smoke do wheel usa `python -m pip`, ausente em venvs
  criados pelo uv.

## [0.14.0] — 2026-10-15

### Adicionado

- Módulo `project` para carregamento sem execução, `artifacts` para IO protegido e
  `evidence` para interpretação comum de resultados por regra (AD-006).
- Verificação de imports Python por AST e resultado por regra; erros de leitura ou
  sintaxe reprovam a análise. Novas regras ARCH-004 e ARCH-005 protegem o carregador.
- Teste do wheel instalado fora do checkout e smoke de CLI, catálogo, analyze e guide.
- Registro de auditoria com alcance explícito, regressões e limites em `docs/auditoria-2026-10.md`.
- CI inclui Python 3.14 e análise estática; release exige tag igual à versão e testes
  antes da publicação. Permissão padrão de workflows limitada a leitura.

### Corrigido

- Escrita de relatórios não segue links simbólicos fornecidos pelo checkout; gravação
  atômica por arquivo, compartilhada com geração e atualização de arquivos.
- Todos os números de contratos precisam ser finitos, inclusive thresholds e custos.
- YAML/JSON rejeitam chaves duplicadas; JSONL exige run inteiro positivo e trata IO inválido.
- Evals não apagam recursivamente o results_dir; limpam somente artefatos declarados e
  recusam diretórios que põem fontes, specs ou datasets em risco.
- Mutação recusa alvos resolvidos fora da cópia, inclusive durante a restauração.
- Comparação YAML preserva cerquilhas dentro de strings literais e tolera documentos atípicos.

### Migração

- `core.load` e `core.Project` permanecem compatíveis. Caminhos de artefatos e datasets
  devem ser relativos ao projeto; limites infinitos e configurações ambíguas agora reprovam.
- `rule_results` acrescenta evidência por regra ao relatório existente; comandos e
  estados principais permanecem. Copiar o projeto não constitui sandbox de comandos.

## [0.13.0] — 2026-10-15

### Adicionado

- `sdd analyze`: diagnósticos estáticos e matriz critério → tarefa em JSON/Markdown,
  inclusive com specs inválidas; cenários repetidos geram aviso determinístico.
- `sdd guide <feature> --stage clarify|plan|implement|converge`: contexto para o agente,
  sem executar comandos nem alterar arquivos. Implementação e convergência ficam
  bloqueadas por erros estáticos; declarações não são evidência executada.
- Instruções de adoção e documentação do fluxo inspirado no GitHub Spec Kit.
- Feature de fluxo guiado com AC-094 a AC-099 e integração à adoção no AC-100.

### Corrigido

- `diff` preserva nomes com acentos, espaços e caracteres de controle ao consumir
  saídas Git separadas por NUL, impedindo aprovações indevidas por caminhos escapados (AC-101).
- `eval` reprova scores NaN, infinitos, booleanos e valores não numéricos, além de
  agregações não finitas, como `INCOMPLETO`; não grava agregados inválidos (AC-102).

## [0.12.0] — 2026-10-14

### Adicionado

- Exceções `SDD-No-Spec-Change(feature): motivo`, limitadas à feature nomeada.
- Relatórios versionados de check, diff, mutate, eval e arch: `tool_version`,
  `report_version: 1` e `command`; o JSON da mutação preserva a lista por feature.
- Relatórios próprios de diff e arquitetura, com resultado e constituição.

### Modificado

- Constituição distingue `DECLARADO`, `PENDENTE`, `APROVADO`, `VIOLADO`,
  `NÃO_APLICÁVEL` e `MANUAL`; referências `kit:*` não implicam execução.
  **Migração:** consumidores que esperavam `COBRADO` devem interpretar os novos estados.
- O trailer global reprova por padrão. Migração temporária via
  `allow_global_diff_override: true`, com aviso de depreciação. Exceções não liberam
  datasets alterados sem spec nem código sem dono.
- AD-005 substitui AD-001: verificação por ferramentas e agregação determinística
  coexistem com evidência probabilística de juiz LLM explicitamente habilitado.
- Specs divididas em oito capacidades com paths próprios e IDs preservados;
  tarefas obrigatórias também no próprio kit. Novos critérios AC-089 a AC-093.
- Temporários dos filhos do mutate ficam privados à cópia; perda da cópia
  reprova como execução incompleta mesmo com min_score baixo (AC-093).
- Caminho temporário do mutate corrigido na spec e contagem do README substituída
  pela contagem calculada por `sdd validate`.

## [0.11.0] — 2026-10-13

### Adicionado

- `sdd diff` compara a spec de forma **semântica**: edição que só muda comentário, espaço
  em branco ou ordem de chaves não conta como mudança de spec e não libera código alterado
  (AC-087). YAML ilegível cai para comparação textual e conserva a regra toda.
- `sdd mutate` limpa cópias de trabalho órfãs (`/tmp/sdd-mutate-*` de execuções mortas à
  força, mais velhas que 24 h) ao iniciar; execuções concorrentes recentes são preservadas
  (AC-088). A cópia de um run que falha no meio da criação também não deixa lixo.
- Exemplo `examples/pytest/`: rastreio de IDs verificado no CI com pytest 8+ e
  `--junitxml`, cobrindo a stack Python de primeira classe (antes só jest, vitest e Go).

### Modificado

- `docs/verificacao.md` e `docs/limites-e-creditos.md` documentam a comparação semântica
  do diff e o sweep de cópias órfãs do mutate.
- CI (`job exemplos`) instala `.[dev]` e roda `sdd check` no exemplo pytest.

## [0.10.0] — 2026-10-13

### Adicionado

- Adoção gradual: `sdd init --preset minimo|padrao|completo` e `sdd enable <camada>`
  para ligar camadas num projeto existente (design, tasks, constitution, arch, decisions,
  evals, mutate, strict, agentes), sem sobrescrever nada (AC-083 a AC-086).
- CLI mais enxuta: `--version`, saída de veredito limpa no CI e documentação alinhada.

## [0.9.0] — 2026-10-13

### Adicionado

- Tarefas com evidência (`tasks` + `evidence`), critério vago detectado no `validate`
  e `SDD-Fix: AC-012` no `diff` (correção de bug exige teste de regressão que cite o ID)
  (AC-060s).
- Constituição executável (`constitution.yaml`): princípios com `enforced_by` apontando
  regras ARCH, gates ou `manual dependendo o estágio`; cobrada no `check`.
- Tamanho de spec muito diferente do ritmo de mudança reprova (`small` com muitos arquivos).

## [0.8.0] — 2026-10-13

### Adicionado

- Perfil de agentes de IA (`sdd enable agentes`): catálogo SPEC-BASE v0.1 como matriz
  verificável — 12 módulos (núcleo, ferramentas, recuperação, memória, humano no laço,
  delegação, produção, LGPD/PL 2338...), 61 requisitos com evidência declarada por ID
  de AC, NFR ou EVAL, ou `not_applicable` com motivo; cobrado por `validate` e `check`.
- Testes do perfil ajustados por caminho no Windows (config via YAML).

## [0.7.0] — 2026-10-13

### Adicionado

- `sdd specify <nome>`: esqueleto de spec com IDs livres (AC-061...) e campos marcados
  com `PREENCHER:`; placeholder sem resposta bloqueia o `validate`.
- Ablação guiada pela medição de mutação nos testes do kit.

### Corrigido

- Dependabot ligado e dependências dos exemplos atualizadas.

## [0.6.0] — 2026-10-12

### Adicionado

- Regras de arquitetura executáveis (`sdd arch`: `from` → `forbid`/`forbid_paths`) e
  modos de falha declarados com cobertura no `design.dependencies` (AC-040s).
- `sdd mutate` com relatório em `.sdd/mutation.md` e vendeta no resumo do CI.

### Corrigido

- Codificação UTF-8 explícita para rodar no Windows; anotações de teste falho no PR.

## [0.5.0] — 2026-10-12

### Adicionado

- Primeira versão completa do motor determinístico: `sdd init`, `sdd validate`,
  `sdd check` (rastreio AC → teste com o ID no nome, orfans, gates), `sdd diff`
  (código muda sem spec reprova, com trailer `SDD-No-Spec-Change` auditável),
  `sdd mutate` (mutantes de operador matam testes fracos) e `sdd eval`
  (comportamento de LLM medido com intervalo de confiança, sem LLM no veredito).
- Rastreio validado com runners reais de jest, vitest e go no CI.
- Kit verifica a si mesmo: spec do motor (FEATURE-001) cobre o próprio código.

[0.11.0]: https://github.com/lucianoon/sdd-kit/releases/tag/v0.11.0
[0.10.0]: https://github.com/lucianoon/sdd-kit/releases/tag/v0.10.0
[0.9.0]: https://github.com/lucianoon/sdd-kit/releases/tag/v0.9.0
[0.8.0]: https://github.com/lucianoon/sdd-kit/releases/tag/v0.8.0
[0.7.0]: https://github.com/lucianoon/sdd-kit/releases/tag/v0.7.0
[0.6.0]: https://github.com/lucianoon/sdd-kit/releases/tag/v0.6.0
[0.5.0]: https://github.com/lucianoon/sdd-kit/releases/tag/v0.5.0
