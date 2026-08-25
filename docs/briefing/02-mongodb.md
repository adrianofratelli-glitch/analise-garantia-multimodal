# Análise de Garantia com IA — MongoDB: modelo, índices e busca

> Segunda parte do briefing. As quatro coleções, os três tipos de índice, os validadores e o critério de identidade que eu só acertei medindo.

---

## Modelo de dados

| Coleção | Conteúdo |
|---|---|
| `pedidos` | pedidos e itens, com SKU e categoria. Validador `$jsonSchema` |
| `catalogo` | catálogo de checklist de defeito por categoria |
| `catalogo_fotos` | fotos de referência por SKU, com embedding multimodal |
| `chamados` | casos: checklist, descrição, imagem, fotos extras, embedding, veredito, identidade, status. Validador `$jsonSchema` |

Estados de `chamados`: `em_analise` → (revisão humana) → `resolvido`.

O ciclo de precedente vive nessa transição: só caso `resolvido` entra no filtro da recuperação. Veredito não revisado nunca vira base pro próximo.

## Índices — `setup_indexes.py`, nomes vindos do `.env`

**Regulares:**

- `status + created_at` — a fila de revisão
- `numero_chamado` (único)
- `numero_pedido` (único)
- `categoria` (único, em `catalogo`)
- `sku + foto_idx` (único, em `catalogo_fotos`)

**Vetoriais:**

- `defeitos_vector_index` — em `chamados.embedding`, com `categoria` e `status` como **filtro nativo**. É o que permite recuperar só precedente da mesma categoria e já resolvido, sem pós-filtro.
- `catalogo_fotos_vector_index` — em `catalogo_fotos.embedding`.

**Atlas Search:**

- `chamados_text_index` — e **é necessário pro `$rankFusion`**, não é opcional.

Nesse último, `descricao_cliente` e `frase_analise` são `string` (analisados), mas `categoria` e `status` são **`token`**: são enum, e o que eu quero é `equals` exato. Indexar enum como texto analisado traz falso positivo por stemming e você descobre isso num precedente estranho no meio da demo.

## Validadores `$jsonSchema`

O de `chamados` cobra o que importa: `status` como enum, `classificacao` como enum, `confianca` entre 0 e 1, `revisao_humana` booleano obrigatório, e o `embedding` com **exatamente** `EMBEDDING_DIM` doubles.

Esse último é o que pega o erro clássico de trocar o modelo de embedding e só descobrir quando a busca começa a devolver bobagem.

Default é `validationAction=error`. `warn` existe só pra migrar seed antigo, via variável de ambiente explícita — não é o padrão. Validador que só avisa é decoração.

## Recuperação de precedentes

Filtro sempre `{categoria, status: "resolvido"}`, aplicado como filtro do índice.

Dois modos:

- **`vector_search`** — `$vectorSearch` puro sobre `chamados.embedding`.
- **`hybrid_search`** — `$rankFusion` combinando a perna vetorial com o Atlas Search full-text, numa agregação só.

O `$rankFusion` degrada pra `vector_search` **só quando a causa é ausência de suporte ou de índice** (o cluster não conhece o estágio, ou o índice de texto não existe). Qualquer outro erro — conexão, timeout — sobe normal pro Banner.

Fallback que engole erro de infraestrutura transforma "o cluster está fora" em "os resultados ficaram meio estranhos hoje". E quando cai no fallback, o `funnel` diz isso na tela, com o motivo.

O `funnel` que volta pra UI carrega: quantos candidatos, qual o filtro aplicado, quantos voltaram, e por qual modo. Se eu não conseguir mostrar o afunilamento, "busca vetorial" continua sendo palavra.

## Identidade do produto — o critério é relativo, e isso foi medido

Essa é a parte que eu só aprendi medindo, e que **não pode ser simplificada de volta**:

> **Threshold absoluto sozinho não funciona aqui.** Foto de produto em estúdio — fundo branco, mesma iluminação — faz qualquer par de móveis pontuar alto no embedding multimodal. A métrica captura "isso é foto de produto de mobília", não a identidade fina do item. Uma cadeira de plástico contra o SKU de uma cadeira gamer já pontuou **0.83**, perigosamente perto da faixa de "mesmo produto" (~0.92–0.94) que eu tinha medido antes.

Então o sinal principal é **relativo**:

1. busca contra o catálogo **inteiro**, sem filtro de SKU;
2. agrupa o melhor score por SKU;
3. exige que o SKU reivindicado seja **o melhor match entre todos** (ou empate dentro de uma margem de 0.01).

O piso absoluto de 0.80 continua ali, mas só como backstop pro caso raro do produto não ter parente nenhum no catálogo.

Os dois modos de falha são **distintos** e a UI precisa separá-los, porque a ação do analista é diferente:

- "essa foto parece mais com o SKU X do que com o do pedido" → provável upload errado;
- "é o melhor match do catálogo mas ainda assim está baixo" → pode não ser produto conhecido.

E se o catálogo não tiver foto seedada, devolve `score: null` e **não bloqueia o fluxo** — etapa pulada, dito na tela.

## Embedding

Voyage `voyage-multimodal-3.5`, **1024 dimensões**, gerado a partir da frase natural (`compor_frase`) + a imagem PIL já normalizada.

O mesmo JPEG normalizado vai pro storage, pra Voyage e pro Claude. Não regera em cada etapa.

E o contrato que importa: **`compor_frase` no seed e em runtime tem que ser a mesma função**. Frase montada diferente = espaço vetorial diferente = recuperação degradando sem erro nenhum aparecer.

## Change Stream para a fila ao vivo

`GET /api/chamados/stream` (SSE) em cima de um Change Stream do Atlas. Sem polling, sem fila de mensagem, sem componente extra.

Duas coisas no stream que valem a pena:

- Põe `$project` **dentro do pipeline do Change Stream**. Sem isso cada evento carrega o `fullDocument` inteiro pela rede — incluindo o embedding de 1024 floats — a cada chamado aberto.
- O evento serve de **gatilho**, não de payload: o front recebe e chama `GET /api/chamados/pendentes` de novo. Assim a fila fica sempre consistente com o banco, mesmo se um evento se perder ou chegar fora de ordem.

## Health e analytics

O `/api/health` faz o count por status com **um `$group`**, não com três `count_documents`. A página faz poll a cada 10s; três scans completos por poll é desperdício que aparece na fatura.

O `/api/analytics` é Aggregation Pipeline sobre os `_meta` gravados em cada veredito (modelo, latência, tokens, precedentes usados). Se o `_meta` não for gravado na análise, essa página vira estimativa — e estimativa não é analytics.

## Seeds

```bash
seed_meta.py            # pedidos + catalogo
seed.py                 # chamados resolvidos (embeda as imagens deles)
seed_catalogo_fotos.py  # fotos de referência por SKU
setup_indexes.py        # regulares + vetoriais + text search + validadores
```

As fotos de seed **não vão pro repositório** — `SEED_IMAGES_DIR` aponta pra uma pasta local.
