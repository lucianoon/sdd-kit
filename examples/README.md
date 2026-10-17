# Exemplos por stack

Cada pasta é um projeto sdd independente, verificado no CI a cada commit
(job `exemplos`), para provar que o rastreio funciona fora do Python.

| Pasta | Runner | Como o JUnit é gerado | Convenções de nome reconhecidas |
|---|---|---|---|
| `rag/` | pytest + EVALs offline | `--junitxml` + harness JSONL | RAG autorizado, traces, manifesto e comparação de versões |
| `pytest/` | pytest 8+ | `--junitxml` | `test_ac_001_...`, `def testAC001`, IDs em parametrize |
| `multi/` | pytest 8+ | `--junitxml` | duas specs independentes (`pedidos`, `fretes`) com código realmente acoplado |
| `jest/` | jest 30 | jest-junit 17 | `it("AC-001 ...")`, `describe("AC-003 ...")`, `test.each("AC-004 ...")` |
| `vitest/` | vitest 5 | reporter `junit` nativo | as mesmas do jest |
| `go/` | go test | go-junit-report | `TestAC_001_X`, `TestAC001X`, `t.Run("AC-003 ...")` |

Para rodar um exemplo: entre na pasta, instale as dependências (`npm install` ou
`go install github.com/jstemmer/go-junit-report/v2@v2.1.0`) e rode `sdd check`.

Dependências: versões fixas, com pelo menos duas semanas de publicação e auditadas com
`npm audit`. O exemplo do vitest usa `legacy-peer-deps` (no `.npmrc`) por um bug do
resolvedor do npm 10 com os peers do vitest 5, e por isso declara o `vite` explicitamente.
O jest ainda traz um alerta moderado transitivo (sprintf-js, via istanbul) sem versão
corrigida publicada; é dependência só de teste deste exemplo.
