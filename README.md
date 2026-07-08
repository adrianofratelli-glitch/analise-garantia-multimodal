# MM — Análise de Garantia (PoV MadeiraMadeira)

Triagem de defeitos de produto com IA: o cliente informa o pedido, marca o
checklist, descreve e envia uma foto; a IA classifica a causa provável
(**defeito de fábrica / transporte / mau uso / inconclusivo**) usando precedentes
históricos recuperados por busca vetorial — sempre sujeita a revisão humana (CDC).

## MongoDB como motor de todas as camadas

| Camada | Onde vive |
|---|---|
| Pedidos (lookup) | collection **`pedidos`** |
| Catálogo de defeitos (checklist) | collection **`catalogo`** |
| Chamados + veredito + embedding | collection **`chamados`** |
| Busca semântica | **Atlas Vector Search** (`$vectorSearch`, índice `defeitos_vector_index`) |
| Busca híbrida | **`$rankFusion`** (vetorial + Atlas Search full-text `chamados_text_index`) |
| Fila em tempo real | **Change Streams** (SSE) |
| Analytics | **Aggregation Pipeline** (pronto para Atlas Charts) |

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
./.venv/bin/python seed_meta.py      # pedidos + catalogo
./.venv/bin/python seed.py           # 15 chamados resolvidos (embeda as imagens)
./.venv/bin/python setup_indexes.py  # índices: regulares + vetorial + texto
```

## Rodar

```bash
./start.sh        # backend :8100 + frontend :5190 (dev)
# smoke test do pipeline completo:
cd backend && ./.venv/bin/python test_http.py
```

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
