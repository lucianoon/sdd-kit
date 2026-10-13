# Exemplos por stack

Cada pasta é um projeto sdd independente, verificado no CI a cada commit
(job `exemplos`), para provar que o rastreio funciona fora do Python.

| Pasta | Runner | Como o JUnit é gerado | Convenções de nome reconhecidas |
|---|---|---|---|
| `jest/` | jest 29 | jest-junit | `it("AC-001 ...")`, `describe("AC-003 ...")`, `test.each("AC-004 ...")` |
| `vitest/` | vitest 2 | reporter `junit` nativo | as mesmas do jest |
| `go/` | go test | go-junit-report | `TestAC_001_X`, `TestAC001X`, `t.Run("AC-003 ...")` |

Para rodar um exemplo: entre na pasta, instale as dependências (`npm install` ou
`go install github.com/jstemmer/go-junit-report/v2@v2.1.0`) e rode `sdd check`.
