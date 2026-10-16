# Comportamento de LLM

Critérios estatísticos para o que um teste isolado não prova (`sdd eval`).

## Sistemas com LLM: `sdd eval`

Testes cobrem o código ao redor do modelo. O comportamento do modelo (escolher a tool
certa, não alucinar, seguir o formato) varia entre execuções: um teste que passa uma vez
não prova nada. Para isso, a spec declara **evals**:

```yaml
evals:
  - id: EVAL-001
    metric: tool_selection_accuracy
    dataset: evals/datasets/tools.jsonl   # versionado no repo; cada linha com "id" único
    min_cases: 200                        # casos distintos exigidos em CADA execução
    runs: 3                               # execuções independentes
    threshold: {min: 0.9}                 # ou {max: 0.02} para taxas ruins (ex. alucinação)
    max_run_spread: 0.05                  # reprova se variar demais entre execuções
    use_lower_bound: true                 # compara o limite inferior do IC 95%, não a média
    judge: deterministic                  # ou llm (ver abaixo)
```

**O harness é seu**, em qualquer linguagem e com qualquer SDK. Ele só grava resultados
**brutos**, um por caso e execução, em `.sdd/evals/EVAL-001.jsonl`:

```json
{"case": "c17", "run": 1, "pass": true}
{"case": "c17", "run": 2, "pass": false}
```

(ou `"score": 0.82` com `aggregate: mean_score`). **O harness não declara a nota:** o
`sdd eval` calcula tudo e confere a integridade:

| Veredito | Quando |
|---|---|
| `OK` | dentro do limite e estável |
| `FORA_DO_LIMITE` | média (ou limite do IC 95%) fora de `threshold` |
| `INSTAVEL` | maior − menor valor entre execuções acima de `max_run_spread` |
| `INCOMPLETO` | menos execuções ou casos que o exigido, caso fora do dataset, caso duplicado, score inválido ou agregação não finita |
| `SEM_RESULTADO` | harness não gravou o arquivo (resultados antigos são apagados antes) |

Com `mean_score`, cada `score` deve ser um número finito: `NaN`, infinitos,
booleanos, strings e valores ausentes reprovam. Se a soma ou a variação produzir um
valor não finito por overflow, a eval também reprova como `INCOMPLETO`, sem publicar
agregados inválidos. Scores finitos seguem a escala da métrica e os limites da spec.

Os limites configurados (`threshold.min/max`, `max_run_spread`) também precisam ser
finitos. JSONL com chaves duplicadas é inválido; `run` deve ser inteiro positivo,
sem coerção de string, float ou booleano. Arquivo ilegível retorna `INCOMPLETO`.

`evals.results_dir` fica dentro do projeto, fora de fontes/specs/datasets e sem links
simbólicos. Antes do harness, apenas os JSONL dos EVALs declarados são removidos;
arquivos vizinhos permanecem. Caminho inseguro reprova antes de executar o harness.

```
$ sdd eval
OK              EVAL-001  tool_selection_accuracy = 0.913
FORA_DO_LIMITE  EVAL-002  hallucination_rate = 0.041  (média 0.041 > máximo 0.02)
REPROVADO — relatório em .sdd/eval.md
```

Por que o **intervalo de confiança** importa: 87% de acerto em 30 casos parece passar num
mínimo de 85%, mas o IC 95% vai de ~79% a ~92%. Com `use_lower_bound: true` o sdd só aprova
quando até o cenário pessimista está acima do limite. Isso obriga datasets do tamanho certo.

**Travas contra afrouxar a régua:**
- `sdd validate` exige que o dataset exista, tenha IDs únicos e pelo menos `min_cases` casos.
- `sdd diff` reprova PR que altera o dataset de um eval sem alterar a spec.
- Coloque prompts e config do modelo nos `paths` da feature: trocar prompt sem atualizar a
  spec também reprova no `diff`.

**Juiz LLM.** Algumas qualidades só são medíveis por outro modelo ("a resposta é fiel ao
documento?"). O kit permite, de forma explícita e auditável (decisão AD-004):
`judge: llm` só é aceito com `evals.allow_llm_judge: true` na config; a agregação continua
determinística, mas a evidência e a aprovação do eval dependem do julgamento do modelo.
O JSON registra `probabilistic: true` e o Markdown marca o resultado como
**evidência probabilística**, recomendando revisar uma amostra. ACs e NFRs nunca usam juiz LLM.

`sdd eval` fica fora do `sdd check` porque chama APIs de LLM (custo, tempo, segredo).
O workflow gerado traz o passo comentado.
