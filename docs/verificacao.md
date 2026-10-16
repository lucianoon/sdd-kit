# Verificação contínua

Divergência entre código e spec (`sdd diff`), tratamento de mudanças e força dos testes (`sdd mutate`).

### Tratamento de mudanças

| Situação | O que fazer | O `sdd diff` cobra |
|---|---|---|
| Mudou o comportamento desejado | atualize a spec primeiro | spec alterada junto com o código |
| Bug: código descumpre uma spec correta | corrija e acrescente teste de regressão | `SDD-Fix: AC-012` no commit **e** um arquivo de teste alterado que cite `AC-012` |
| Mudou só a solução técnica | preserve o comportamento | `SDD-No-Spec-Change(nome-da-feature): <motivo>` no commit |

Correção sem teste de regressão reprova: "corrigi" sem um teste que pegaria o bug de volta
não comprova nada. Onde ficam os testes: `tests.paths` em `specs/sdd.yaml` (padrão cobre
`tests/`, `test_*.py`, `*_test.go`, `*.test.*`, `*.spec.*`, `src/test/`).

## Divergência: `sdd diff`

O `check` garante que a spec atual está coberta. O `diff` garante que ela **continua sendo
a verdade** quando o código muda. Cada spec declara o código que é dela:

```yaml
# specs/features/FEATURE-001/spec.yaml
paths: ["src/pedidos/**"]
```

```yaml
# specs/sdd.yaml
code: ["src/**"]     # o que conta como código de produção
```

```bash
sdd diff --base origin/main
```

Compara com o merge-base da branch alvo, incluindo alterações não commitadas e arquivos
não rastreados.

A listagem do Git usa separação por NUL (`-z`): nomes com acentos, espaços, aspas ou
caracteres de controle permitidos pelo sistema são preservados, inclusive com
`core.quotePath` ativo. Esses nomes passam pelas mesmas regras de propriedade e spec.

| Situação | Resultado |
|---|---|
| Arquivo em `paths` de uma feature mudou e a pasta da spec não | **reprova** |
| Arquivo em `code` mudou e nenhuma feature o declara | **reprova** (código sem dono) |
| Código e spec da feature mudaram juntos | aprova |
| Só a spec mudou | aprova com aviso (spec-first é legítimo) |
| Spec editada sem mudar o conteúdo (comentário, espaço, ordem de chaves) e o código mudou | **reprova** — edição cosmética não conta como mudança de spec |
| Arquivo fora de `code` (docs, CI...) | ignorado |

A comparação da spec é **semântica**: o `diff` compara o documento YAML (valores e
estrutura), não o texto. Acrescentar um comentário ou reformatar a spec produz a mesma
 impressão; tais edições não liberam código.

**Refatoração sem mudança de comportamento** não precisa mexer na spec. Declare no commit:

```
refactor: extrai validação de pedido

SDD-No-Spec-Change(pedidos): só reorganização interna, sem mudança de comportamento
```

O diff libera apenas o código da feature `pedidos` e imprime o motivo. Outras features
continuam exigindo mudança na própria spec. Código sem dono e dataset alterado sem spec
sempre reprovam. Feature inexistente e motivo vazio são erros. As exceções ficam no
histórico do Git e em `.sdd/diff.json` e `.sdd/diff.md`; a revisão humana confere o motivo.

**Migração da versão 0.11:** o trailer global `SDD-No-Spec-Change: motivo` reprova por
padrão. Para migrar aos poucos, `allow_global_diff_override: true` na config aceita
temporariamente o formato legado com aviso de depreciação. Exit codes: `0` aprovado, `1` reprovado, `2` erro de git
(ex.: base inexistente; no CI, use `fetch-depth: 0`).

## Qualidade dos testes: `sdd mutate`

O `check` prova que existe um teste com o ID e que ele passa. Não prova que o teste
**verifica** algo: `def test_ac_001(): criar_pedido()` passa sem assert nenhum. O `mutate`
mede a detecção dos operadores amostrados sem LLM:

1. Copia o projeto para um diretório temporário. Os filhos recebem `TMPDIR`, `TEMP`
   e `TMP` privados à cópia; uma limpeza no runner não alcança cópias irmãs.
2. Confere que a suíte passa sem mutações (senão, sai com código 2).
3. Para cada mutante, troca **um** trecho no código dos `paths` da feature e roda os testes.
4. Testes falharam = mutante morto. Passaram = **sobreviveu**: aquele comportamento não é
   verificado por ninguém.

| Grupo | Mutações | Onde |
|---|---|---|
| Comparação e lógica | `>`→`<=`, `==`→`!=`, `and`→`or`, `&&`→`\|\|`... | todas |
| Booleanos | `True`→`False`, `true`→`false` | todas |
| Aritmética | `+`↔`-`, `*`↔`/`, `%`→`*` (só binários: `*args`, ponteiro e `**` ficam) | todas |
| Constantes | inteiro `n`→`n+1` (literais com zero à esquerda ficam) | todas |
| Negação e pertinência | remove `not`, `is`↔`is not`, `in`↔`not in` (o `in` de `for` fica) | Python |
| Negação | remove `!` (`x!`, `macro!`, `!!` e `!=` ficam) | sintaxe C e PHP |
| Retorno | `return <expr>` de uma linha → `return None` / `return undefined` | Python, JS, TS |

A extensão decide a sintaxe: `#` é comentário em Python e Ruby, `//` nas linguagens com
sintaxe C (em Python `//` é divisão inteira; em JS/TS `#` é campo privado). Os `<` e `>` de
tipos genéricos (TS, Java, Kotlin, C#, Rust, C++, Swift, Scala) e de tags JSX não são mutados.

**Mutante que não compila não conta como morto.** Em Python, o candidato com erro de sintaxe é
descartado antes de rodar testes. Nas outras linguagens, configure `mutation.build` (ex.:
`tsc --noEmit`, `go vet ./...`, `cargo check`): o mutante que falha no build fica **inválido**,
fora do score e listado no relatório. Sem `build`, um erro de compilação ainda derruba a suíte
e conta como morto.

```
$ sdd mutate
== pedidos
  killed    src/pedidos/regras.py:12      >=→<
  survived  src/pedidos/regras.py:18      and→or
  score 50% (mínimo 80%)
REPROVADO — relatório em .sdd/mutation.md
```

```yaml
# specs/sdd.yaml
mutation:
  min_score: 0.8
  max_mutants: 50          # amostra determinística e espalhada: mesmo resultado em toda execução
  timeout: 120             # por mutante; estouro (ex.: loop infinito) conta como morto
  command: "pytest -q -x"  # padrão: tests.command. Falhar rápido acelera muito
  build: "npx tsc --noEmit" # opcional: falha aqui = mutante inválido, fora do score
  env:
    PYTHONPATH: "{root}/src"   # pacote instalado em modo editável apontaria para o original
```

- `--base origin/main` muta só os arquivos alterados no PR (é o que o workflow gerado faz).
- `--feature pedidos` limita a uma feature; `--max 20` sobrescreve a amostra.
- Linha com `sdd: no-mutate` é ignorada (para mutantes equivalentes, ex. log).
- Strings, comentários, docstrings e imports não são mutados.

**Custo:** cada mutante roda a suíte. Com uma suíte de 15 s, 50 mutantes levam até ~12 min.
Use um `command` mais rápido (subconjunto, `-x`) e `--base` no CI.

Para mutação mais profunda, ferramentas dedicadas (mutmut, Stryker, pitest, cargo-mutants)
entram como `gates` comuns; o `mutate` embutido existe para funcionar em qualquer stack sem
instalar nada.

Se a suíte apagar a cópia de trabalho e impedir a restauração, o mutate registra
execução incompleta e sai com código 2; uma pontuação parcial nunca aprova esse erro.
