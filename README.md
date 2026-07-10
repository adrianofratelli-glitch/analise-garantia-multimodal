# Análise de Garantia Multimodal

PoV de triagem de defeitos de produto com IA, pensada para qualquer loja que
venda produtos físicos: o cliente informa o pedido, marca o checklist, descreve
e envia uma foto; a IA classifica a causa provável (**defeito de fábrica /
transporte / mau uso / inconclusivo**) usando precedentes históricos recuperados
por busca vetorial multimodal — sempre sujeita a revisão humana (CDC).

Antes de classificar o defeito, a foto do cliente também é comparada (embedding
multimodal Voyage AI) contra as fotos de referência de **todo** o catálogo, não
só do SKU do pedido — o sinal é relativo: o produto do pedido precisa ser o
melhor match entre todos, não só "parecido o bastante" sozinho. Fotos de
produto em estúdio pontuam alto entre si por natureza (mesmo fundo, mesma
iluminação), então um threshold absoluto sozinho deixa passar produto errado
com facilidade — comparar contra o catálogo inteiro é o que realmente separa
"é esse produto" de "é um produto qualquer parecido".

## MongoDB como motor de todas as camadas

| Camada | Onde vive |
|---|---|
| Pedidos (lookup) | collection **`pedidos`** |
| Catálogo de defeitos (checklist) | collection **`catalogo`** |
| Chamados + veredito + embedding | collection **`chamados`** |
| Fotos de referência do catálogo (verificação de identidade) | collection **`catalogo_fotos`** |
| Busca semântica | **Atlas Vector Search** (`$vectorSearch`, índice `defeitos_vector_index`) |
| Busca híbrida | **`$rankFusion`** (vetorial + Atlas Search full-text `chamados_text_index`) |
| Fila em tempo real | **Change Streams** (SSE) |
| Analytics | **Aggregation Pipeline** (pronto para Atlas Charts) |
| Governança de schema | **`$jsonSchema`** validator (`chamados`, `pedidos`) |

As imagens (blobs) ficam **fora** do MongoDB — padrão correto de blob storage.
No PoV ficam em disco local (`backend/media/`, servidas pelo FastAPI); em produção
basta reimplementar `storage.py` com S3 + CDN (a interface `(uri, url)` não muda).

## Stack
- **Backend**: FastAPI + Motor (async), Voyage `voyage-multimodal-3.5` (embedding
  multimodal 1024d), Claude `claude-sonnet-4-6` com **tool use forçado** (veredito
  estruturado, sem parsing frágil de JSON).
- **Frontend**: React + Vite + LeafyGreen (design system MongoDB).
- Tudo parametrizado pelo **`.env`** (DB, collections, índices, modelos).

## Setup (uma vez)

```bash
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt

# popular o MongoDB (lê o .env)
./.venv/bin/python seed_meta.py            # pedidos + catalogo
./.venv/bin/python seed.py                 # 15 chamados resolvidos (embeda as imagens)
./.venv/bin/python seed_catalogo_fotos.py  # 4 fotos de referência por SKU (verificação de identidade)
./.venv/bin/python setup_indexes.py        # índices: regulares + vetorial + texto + $jsonSchema

# opcional: gerar fotos placeholder antes de ter as fotos reais do catálogo
./.venv/bin/python generate_placeholders.py
./.venv/bin/python generate_catalogo_placeholders.py
```

## Rodar

```bash
./start.sh        # backend :8100 + frontend :5190 (dev)
# smoke test do pipeline completo:
cd backend && ./.venv/bin/python test_http.py
```

## Testes e lint

```bash
cd backend
./.venv/bin/pip install -r requirements-dev.txt

./.venv/bin/pytest       # testes unitários (lógica pura, sem Atlas/rede)
./.venv/bin/ruff check .  # lint
```

`test_http.py` continua sendo o smoke test do servidor real (precisa do backend
no ar e do Atlas seedado) — `pytest` cobre a lógica que não depende de rede.

## Endpoints
| Método | Rota | O quê |
|---|---|---|
| POST | `/api/lookup` | pedido → produtos (lê de `pedidos`) |
| GET | `/api/checklist/{categoria}` | itens do checklist (lê de `catalogo`) |
| POST | `/api/analisar` | RAG completo; `modo=vector` (padrão) ou `modo=hybrid` |
| GET | `/api/chamados/pendentes` | fila de revisão |
| POST | `/api/revisar` | revisão humana → resolvido |
| GET | `/api/analytics` | agregações (Atlas Charts) |
| GET | `/api/chamados/stream` | Change Stream (SSE), novos chamados em tempo real |
| GET | `/api/health` | ping + counts + modelo |
