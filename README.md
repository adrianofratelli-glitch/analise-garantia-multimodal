# Multimodal Warranty Analysis — Reference PoV (MongoDB Atlas)

> The application UI runs in **Portuguese** (pt-BR) for the demo. This README is
> in English so the project is easy to browse on GitHub.

A **vendor-neutral** proof-of-value for **multimodal (image + text) search** on
**MongoDB Atlas**. It shows a pattern any use case can reuse when it combines a
**photo + text** to retrieve similar past cases and support a decision:

> A user describes a problem and uploads a **photo**; the app builds **a single
> multimodal vector** (image + text), retrieves the most similar **precedents**
> via **`$vectorSearch`** — with **native filters** in the same stage — and a
> **vision LLM** suggests a verdict, always **subject to human review**.

The example domain is **furniture warranty** (chair / mattress / wardrobe), but
that's just the dataset. Swap the catalog and seed data for your own case
(insurance claims, asset inspection, quality control, e-commerce, visual
diagnostics, etc.) and the rest stays the same.

## Why MongoDB (the differentiator)

MongoDB Atlas is the engine for **every layer** of the application, not just the
vector store:

- **Single system of record.** Orders (`pedidos`), the defect catalog
  (`catalogo`) and cases (`chamados`) are all MongoDB collections — the order
  lookup and the checklist read straight from the database, with no second
  datastore.
- **Data and vectors together.** The 1024-dim `embedding` lives in the **same
  document** as the business data (product, checklist, verdict, metadata). No
  separate vector database to keep in sync.
- **Native `$vectorSearch` with filters.** Vector search and the filters
  (`categoria`, `status="resolvido"`) run **in the same stage** — no data
  movement.
- **Hybrid search (`$rankFusion`).** Vector and full-text (Atlas Search) rankings
  are fused in a single pipeline when the lexical signal matters.
- **Real-time queue (Change Streams).** New cases are pushed to the review queue
  as they arrive, with no polling.
- **In-database analytics (Aggregation).** Verdict distribution, average
  confidence and model latency are computed with an aggregation pipeline — ready
  to plug into Atlas Charts.
- **Operational + flywheel.** A case stored as `em_analise` becomes, after human
  review, a precedent for future searches — in the same cluster.

## Pluggable components (reference implementation)

The PoV is **agnostic** to the LLM, the embedding model and the image store. The
reference implementation uses concrete providers (see `backend/requirements.txt`)
— **swap them for your own**:

| Role | Function in the flow | Configurable in |
| --- | --- | --- |
| **Multimodal embedding** | one 1024-dim vector from image + text | `backend/voyage.py` · `.env` (`EMBEDDING_MODEL`) |
| **Vision LLM** | structured verdict from photo + text + precedents (forced tool use) | `backend/llm.py` · `.env` (`ANTHROPIC_MODEL`) |
| **Image store** | holds the image binary; Mongo keeps only the URI + vector | `backend/storage.py` (local disk by default; swap for S3 + CDN in production) |

> The embedding is multimodal and computed by the **application** (the same vector
> at seed and runtime) — we do **not** use text-only auto-embedding. Database,
> collection, index and model names are all driven by `.env` (`backend/config.py`).

## Architecture

```
order -> product -> checklist + report -> photo
   |
   |- read order + checklist          (Mongo collections: pedidos, catalogo)
   |- compor_frase()                  (same function at seed and runtime -> comparable vectors)
   |- store image                     (image store; Mongo keeps only the URI + metadata + vector)
   |- multimodal embedding (image+text)   (1024 dims, input_type="query")
   |- $vectorSearch / $rankFusion         filter {categoria, status:"resolvido"}
   |- vision LLM verdict (tool use)        {classificacao, confianca, racional, sinais_observados}
   |- store case status="em_analise"  -> human review -> status="resolvido" (becomes a precedent)
```

Image bytes stay **out of the database** on purpose — object storage is the right
tool for blobs. MongoDB holds the reference, the metadata and the vector.

## Layout

```
backend/
  config.py            all settings from .env (db, collections, indexes, models)
  defeitos_catalog.py  catalog seed source + compor_frase() + derivar_tipo_defeito()
  pedidos_data.py      orders seed source
  seed_data.py         resolved cases (precedents) seed source
  voyage.py            multimodal embedding (image + text)
  storage.py           image store -> URI + URL (local disk; swap for S3 in prod)
  db.py                client + collection helpers + safe_query / SafeQueryError
  rag.py               vector_search() and hybrid_search() -> (docs, funnel)
  llm.py               analisar_veredito() — vision LLM with forced tool use
  main.py              FastAPI (lookup, checklist, analisar, revisar, analytics, stream, health)
  seed_meta.py         seeds pedidos + catalogo
  seed.py              seeds chamados (embeds the images)
  setup_indexes.py     creates the indexes (regular + vector + text)
  test_http.py         end-to-end smoke test against a running server
frontend/              React + Vite + LeafyGreen (UI in pt-BR): Portal and Revisão tabs
seed_images/           example images (placeholders)
```

## Environment variables (`.env`)

Copy `.env.example` to `.env` and fill it in. Everything is configurable; the
essentials:

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | Atlas cluster connection string |
| `MONGODB_DB` | database name (default `madeira_madeira`) |
| `ANTHROPIC_API_KEY` · `ANTHROPIC_MODEL` | vision LLM |
| `VOYAGE_API_KEY` · `EMBEDDING_MODEL` | multimodal embedding |

Collection and index names (`MONGODB_COLLECTION`, `MONGODB_CATALOGO_COLLECTION`,
`MONGODB_PEDIDOS_COLLECTION`, `VECTOR_INDEX_NAME`, `TEXT_INDEX_NAME`) and the
embedding dimension default to sensible values and rarely need changing. Images
are stored on local disk by default (`MEDIA_ROOT`) — no cloud account required.

## Run

> Requires network access to the Atlas cluster and the LLM / embedding providers.

### First run — seed the database and create the indexes

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd backend
.venv/bin/python seed_meta.py       # pedidos + catalogo
.venv/bin/python seed.py            # chamados (embeds the images)
.venv/bin/python setup_indexes.py   # indexes: regular + vector + text
cd ..
```

`setup_indexes.py` creates the Atlas Search indexes programmatically; if your
cluster tier or permissions don't allow it, the script prints the JSON to paste
in the Atlas UI.

### Start

```bash
./start.sh    # backend :8000 + frontend :5173 (installs frontend deps on first run)
```

Vite proxies `/api` and `/media` to the backend. Open port 5173 and follow the
flow: **order -> product -> checklist + report -> photo -> verdict**, then the
**Revisão** tab to confirm and resolve.

Smoke-test the whole pipeline against a running server:

```bash
backend/.venv/bin/python backend/test_http.py
```

## Docker (optional)

Single image (nginx serves the frontend build and proxies `/api` + `/media` to
uvicorn):

```bash
docker build -t warranty-analysis .
docker run --rm -p 8080:8080 --env-file .env warranty-analysis
# open http://localhost:8080
```

## Endpoints

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/health` | Atlas ping + counts + model |
| POST | `/api/lookup` | `{numero_pedido}` -> products of the order (from `pedidos`) |
| GET | `/api/checklist/{categoria}` | checklist items (from `catalogo`) |
| POST | `/api/analisar` | multipart (photo + data); `modo=vector` (default) or `modo=hybrid` |
| GET | `/api/chamados/pendentes` | review queue |
| POST | `/api/revisar` | `{numero_chamado, resolucao_final}` -> `resolvido` |
| GET | `/api/analytics` | aggregations (verdict distribution, confidence, latency) |
| GET | `/api/chamados/stream` | Change Stream (SSE) — new cases in real time |

## Notes

- The text that becomes the embedding is produced by `compor_frase()` — the same
  function at seed and runtime, guaranteeing comparable vectors.
- The LLM verdict is a **suggestion** and always goes through **human review**
  before a case becomes `resolvido` (relevant for consumer-protection rules).
- Uploaded images are normalized to JPEG before the embedding and the LLM call;
  the database stores only the reference, never the bytes.
- The images in `seed_images/` are **placeholders**. For a realistic demo, swap
  them for real photos (same base names). Real photos are not versioned (see
  `.gitignore`).
