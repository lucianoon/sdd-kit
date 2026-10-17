# Escopo e simplicidade

## Avaliação em outubro de 2026

O kit tem 19 comandos públicos, 11 specs próprias e diversos tipos de artefato. Para um
projeto recente, a superfície de processo é grande. Há risco de overengineering,
principalmente quando uma pessoa precisa administrar spec, tarefas, revisão, lições e
propostas para uma alteração pequena. Contagem de comandos não é medida de qualidade;
o custo relevante é aprender e manter o fluxo necessário para entregar uma mudança.

O núcleo tem justificativa concreta: carregar contratos, executar ferramentas, ligar
critérios a testes, impedir evidência antiga e produzir relatórios. A mutação também
tem valor, mas rodar a suíte completa por mutante em cada arquivo afetado pode consumir
dezenas de minutos. Seu custo deve ser considerado no feedback do CI.

As camadas de processo precisam demonstrar uso antes de crescer. `change` pode duplicar
um fluxo que já existe em Git/PR. Revisões e lições têm manutenção própria. Integrações
com agentes precisam acompanhar convenções externas. Elas são opcionais; não devem ser
requisito para o projeto mínimo nem justificativa para renomear contratos existentes.

## Decisão desta entrega

As ideias do AI System Design foram implementadas em `examples/rag`, com testes, specs,
EVALs e um quality gate existentes. Não foram acrescentados comandos públicos, campos
no schema central, dependências de runtime, SDKs, conectores de telemetria ou orquestração.

O exemplo fornece recuperação autorizada, cache invalidável, fallback, limites locais,
traces verificáveis, manifesto e comparação. Ele é uma referência adaptável, não uma
nova API pública de produção. Não afirma avaliar um LLM real ou impor orçamento a um
serviço externo. Veja [o exemplo](../examples/rag/README.md).

## Regra para as próximas mudanças

1. Começar com `init`, `specify`, `validate` e `check`. Adicionar guide ou diff quando houver necessidade.
2. Usar ferramentas do projeto em quality gates antes de criar um novo comando do kit.
3. Preferir exemplo e documentação quando o contrato ainda depende do domínio.
4. Promover código ao núcleo somente após uso concreto em mais de um projeto, com
   duplicação observada, interface estável e custo de manutenção compreendido.
5. Manter avaliações com modelo real explícitas, separadas de testes rápidos e com
   política de dados, credenciais e custos própria.
6. Otimizar a execução da mutação quando houver evidência de gargalo, mantendo a régua
   e a cobertura; não baixar limiar apenas para acelerar o merge.

Não removemos comandos existentes nesta entrega: uma simplificação que quebre fluxos
precisa de evidência de uso e plano de migração. A prioridade é reduzir o caminho que o
usuário precisa percorrer, não apenas reduzir ou aumentar o número de arquivos.
