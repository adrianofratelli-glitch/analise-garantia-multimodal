# Análise de Garantia com IA — prompt de construção

> Esse é o briefing que eu entrego **antes de existir uma linha de código**. Não é documentação do que existe: é o que eu daria pra alguém (ou pro Claude) subir a PoV inteira do zero.

Triagem de defeito em garantia para qualquer varejista que venda produto físico: o cliente procura o pedido, marca um checklist, manda foto; o Claude classifica a causa provável **sobre precedentes históricos** recuperados por busca vetorial e híbrida, e o caso vai sempre pra revisão humana. Backend FastAPI em `:8100`, frontend Vite/React/LeafyGreen em `:5190`.

Um cluster fazendo tudo: pedidos, catálogo, casos, `$vectorSearch`, `$rankFusion`, Change Streams via SSE, agregação e `$jsonSchema`. **Nenhum vector DB, motor de busca ou fila separados.**

| Arquivo | O que responde |
|---|---|
| [`docs/prompts/01-arquitetura.md`](docs/prompts/01-arquitetura.md) | os oito passos do `POST /api/analisar`, tool use forçado, o ciclo de precedente, storage fora do banco, via única de erro, módulos do backend, como rodar, ordem de trabalho |
| [`docs/prompts/02-mongodb.md`](docs/prompts/02-mongodb.md) | as quatro coleções, os três tipos de índice, validadores, recuperação e `$rankFusion` com o fallback correto, o critério **relativo** de identidade, Change Stream |
| [`docs/prompts/03-interface-fluxos.md`](docs/prompts/03-interface-fluxos.md) | as duas pontas da demo, estado no shell, componentes, a fila ao vivo, roteiro |

Se for ler só um: o **02**, pelo critério de identidade. Threshold absoluto ali já falhou uma vez.
