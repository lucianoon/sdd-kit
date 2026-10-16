# Auditoria e melhorias — outubro de 2026

O trabalho parte de `233cfd9` e prepara a versão 0.14.0. O objetivo é reduzir
aprovações indevidas, preservar arquivos do operador e tornar as responsabilidades
internas verificáveis. A [arquitetura interna](arquitetura-interna.md) descreve os
contratos resultantes e os limites de proteção.

## Alcance da revisão

A auditoria de segurança foi estática e cobriu todos os módulos Python do produto
e os workflows críticos. A cobertura registrada foi parcial: 61 dos 100 arquivos
versionados da revisão base foram lidos integralmente. Os outros 39 arquivos,
principalmente documentação, specs, testes e lockfiles, ficaram explicitamente
fora da revisão integral de segurança. Houve revisão funcional adicional e
execução de testes durante a implementação; isso não transforma a auditoria
estática em uma revisão exaustiva nem substitui revisão independente.

Foi confirmado um problema de severidade média, CWE-59: um checkout podia fornecer
`.sdd` ou o destino de relatório como link simbólico e fazer `sdd analyze`
sobrescrever um arquivo externo acessível ao operador. O comando de análise não
precisava executar código do projeto para produzir esse efeito.

A correção centraliza escrita atômica e validação de caminhos em `artifacts`.
Os testes AC-111 exercitam links no diretório e nos destinos JSON/Markdown,
inclusive com configuração inválida, e verificam que arquivos externos continuam
intactos. No POSIX, descritores de diretório e `O_NOFOLLOW` também protegem o
percurso entre validação e escrita. O fallback sem `dir_fd` e a ausência de
`Path.is_junction` são exercitados separadamente para compatibilidade.

## Mudanças de arquitetura e comportamento

| Área | Resultado |
|---|---|
| Carregamento | `project` lê contratos e reúne diagnósticos sem depender do executor; a API pública de `core` permanece compatível. |
| Dados | YAML e JSON recusam chaves duplicadas; limites numéricos são finitos; `run` de eval é inteiro positivo. |
| Evidências | `evidence` interpreta resultados por regra para CLI, check, constituição e riscos. |
| Imports Python | AST reconhece imports relativos, absolutos locais, multilinha e submódulos; erros de leitura/sintaxe reprovam a regra. |
| Evals | Limpeza remove somente resultados declarados; protege fontes/specs/datasets e permite repetir uma execução em pasta personalizada. |
| Mutação | Alvos e restauração devem permanecer dentro da cópia de trabalho. |
| Distribuição | Wheel instalado fora do checkout exercita CLI e recursos; catálogo incompleto bloqueia o smoke. |
| Release | Tag deve corresponder à versão; validação, check, build e smoke antecedem publicação. |

## Validação reproduzível

No macOS com Python 3.14, o check final aprovou 418 testes, sem falhas ou pulos,
e os 115 critérios rastreados. A análise aprovou cinco regras de arquitetura
sobre 21 arquivos, e a análise estática não encontrou erros ou avisos.

Com o ambiente de desenvolvimento instalado (`python -m pip install -e ".[dev]"`):

```sh
sdd validate
sdd analyze
sdd arch
PYTHONWARNDEFAULTENCODING=1 PYTHONWARNINGS=error::EncodingWarning sdd check
python -m build --no-isolation
python scripts/smoke_dist.py dist/*.whl
sdd check -C examples/pytest
sdd check -C examples/multi
```

As quatro specs do checkout local de `valida-docs` também foram carregadas sem
erros ou avisos; seus comandos e testes não foram executados nesta validação.
Os jobs Windows, Linux e macOS estão configurados no CI. Execução local em macOS
não comprova o resultado desses jobs remotos.

## Mutação amostrada

As primeiras suítes por feature deixaram mutantes sobreviverem. Algumas não
incluíam testes existentes dos módulos compartilhados; outras expuseram lacunas
reais nos testes de caminhos internos, fallback de plataforma, imports de
submódulos e distribuição. As suítes foram ampliadas e essas lacunas receberam
regressões comportamentais. Os relatórios locais preservam as rodadas originais;
o limite mínimo de score do projeto não foi reduzido.

Duas variantes equivalentes do módulo `artifacts` são explicitamente excluídas
com `sdd: no-mutate`: o padrão `deep` para os mapas não recursivos aceitos pelo
contrato e a opção de `stat` que não muda o resultado protegido por `confined`
e substituição atômica. Isso não exclui os testes de links nem a proteção real.
O score continua limitado aos candidatos escolhidos e à suíte declarada em cada
execução; não mede cobertura integral de comportamentos.

Resultado consolidado: **91 mutantes mortos pelos testes e dois encerrados por
timeout**, entre 93 selecionados nas oito features alteradas abaixo. O motor conta
timeout no score; portanto, 100% não significa 93 falhas de asserção. As execuções
usaram limite de 12 por feature e suítes focadas declaradas
nos relatórios locais `.sdd/audit-mutation*.json`. Os relatórios originais e a rodada
intermediária também permanecem disponíveis localmente, incluindo reprovações.

| Feature | Mutantes executados | Score amostrado |
|---|---:|---:|
| artefatos | 9 | 100% |
| arquitetura | 12 | 100% |
| evals | 12 | 100% |
| diff | 12 | 100% |
| verificacao | 12 | 100% |
| governanca | 12 | 100% |
| adocao | 12 | 100% |
| mutacao | 12 | 100% |

## Limites restantes

Comandos de testes, gates e harnesses têm a autoridade do operador. O kit não é
um sandbox para código hostil. JS/TS e Go conservam as limitações do parser
textual. Relatórios JSON e Markdown são atômicos individualmente, sem transação
conjunta. Configurações de proteção de tags, ambiente de publicação e trusted
publisher dependem de GitHub e PyPI. Superioridade sobre outros projetos exige
comparações reproduzíveis com critérios e versões definidos.
