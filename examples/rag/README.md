# RAG offline: contratos e evidências

Exemplo completo usando os comandos existentes do SDD Kit. Recuperação lexical local,
respostas de fixture que citam o documento e nenhum SDK, rede, credencial ou modelo real.
Instale o kit e pytest; a partir desta pasta:

```bash
sdd validate
sdd check
sdd eval
python evaluate.py run --out .sdd/baseline
python evaluate.py compare .sdd/baseline .sdd/evals
python evaluate.py benchmark .sdd/evals --max-p95-ms 1000
```

`check` executa os testes e o gate de latência, que produz uma execução nova antes de
medir. `eval` executa o harness e agrega os resultados com o motor existente. O CI roda
a sequência acima. Não é preciso habilitar o catálogo completo de agentes.

## O que o exemplo demonstra

| Contrato | Evidência |
|---|---|
| Isolamento e citações | Dois tenants fazem a mesma pergunta e recebem somente sua fonte e versão |
| Falta de fonte | Pergunta desconhecida, documento revogado ou sem permissão resultam em abstenção |
| Cache | Fonte atualizada, removida ou permissão revogada não reutilizam a resposta anterior |
| Resiliência | Falha do primário usa fallback com o mesmo contrato; falha dos dois resulta em abstenção |
| Trajetória | Auditoria rejeita operação proibida, tenant divergente, ordem inválida e ação após cancelamento |
| Orçamentos | Execução limita chamadas e passos; deadline é verificado nas fronteiras das etapas |
| Avaliação | Quatro EVALs: resultado exato, recuperação correta, trajetória e validade das citações |
| Performance | p95 pelo método nearest-rank sobre durações medidas, separado da média |

O cancelamento implementado ocorre na admissão, antes de qualquer chamada. A auditoria
rejeita traces com ação após cancelamento, mas não interrompe um serviço remoto.
Os limites são cooperativos; esta fixture não é um sandbox ou executor de tarefas.

## Artefatos de avaliação

`cases.jsonl` tem sete casos artificiais em categorias. Cada caso roda três vezes,
a frio, para que cache de outro caso não esconda falhas. Repetir fixtures determinísticas
não constitui evidência estatística de confiabilidade de um modelo.

Em `.sdd/evals/`:

- `EVAL-001.jsonl` a `EVAL-004.jsonl`: resultados brutos por caso/run para `sdd eval`.
- `results.jsonl`: scores por caso, execução, categoria e métrica.
- `traces.jsonl`: operações, status, escopo, duração e custo da fixture.
- `manifest.json`: hashes do dataset, corpus, config, contrato textual e código,
  configuração efetiva, versão do Python, casos, runs e hashes dos artefatos.

`prompt.txt` documenta o contrato da fixture; não é enviado a um modelo. `config.json`
identifica apenas as implementações realmente disponíveis. O harness recusa rotular a
fixture como uma API real. Trocar para um LLM exige outro harness e avaliação apropriada.

Os traces não gravam perguntas ou respostas, só identificadores e hash da pergunta.
Hash de texto previsível não é anonimização; os próprios datasets e IDs também exigem
política de dados se este exemplo for adaptado para informações reais.

## Baseline e candidata

Guarde a baseline antes de alterar a implementação. Gere a candidata em outro diretório:

```bash
python evaluate.py run --out .sdd/baseline
# Altere a implementação ou o contrato textual e revise as specs pertinentes.
python evaluate.py run --out .sdd/candidate
python evaluate.py compare .sdd/baseline .sdd/candidate
```

A comparação verifica integridade, cobertura, tipos de score e pares caso/run.
Dataset, corpus, scorer, juiz e quantidade de execuções devem ser compatíveis.
Mudanças de implementação/configuração são reportadas. Uma piora em qualquer métrica
de um caso reprova, mesmo que a média global melhore. O relatório identifica a categoria.
Os EVALs absolutos continuam obrigatórios: baseline e candidata igualmente ruins não
são aprovadas por apenas empatarem. A comparação não é teste de significância estatística.

Diretórios de saída precisam estar sob `.sdd/`. Reexecutar no mesmo diretório substitui
os artefatos; use nomes distintos e versionamento externo para guardar experimentos.
Escrita é atômica por arquivo; interrupção entre arquivos é detectável pelos hashes.
Hashes detectam alterações acidentais, não autenticam o emissor nem impedem falsificação
deliberada de um manifesto e seus resultados. O harness continua sujeito a revisão.

## Limites de métricas

O custo é zero porque não há chamadas faturáveis. A auditoria detecta valores inválidos
ou acima do orçamento no registro, sem comprovar uma fatura externa. A latência é a da
fixture local, com poucos casos e sem carga concorrente. TTFT fica explicitamente nulo.
Não anuncia desempenho, qualidade generativa, embeddings, busca semântica ou capacidade
de produção de um LLM. `retrieval_correctness` confere o conjunto esperado; não é uma
implementação de Recall@k ou de um juiz genérico de fidelidade.

Inspirado nos tópicos de arquitetura do
[AI System Design, de Amit Shekhar](https://github.com/amitshekhariitbhu/ai-system-design).
Código, fixtures e contratos são implementação própria; nenhum texto ou código do guia
foi copiado. O projeto de origem usa Apache-2.0; este exemplo segue a licença do kit.
