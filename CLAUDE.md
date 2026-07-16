# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Generic PoV for warranty defect triage using AI, usable by any retailer selling physical products. Customer looks up an order, checks a defect checklist, describes the issue, uploads a photo. Before classification, that photo is also compared against the catalog's reference photos for the SKU (Voyage multimodal embedding + `$vectorSearch` on `catalogo_fotos`) as a separate "is this even the right product?" signal. Claude then classifies probable cause (**defeito de fábrica / transporte / mau uso / inconclusivo**) using historical precedents retrieved via vector search — always flagged for human review (CDC compliance requires it in Brazil).

## Commands

```bash
# one-time setup
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python seed_meta.py      # seeds pedidos + catalogo collections
./.venv/bin/python seed.py           # seeds 15 resolved chamados (embeds their images)
./.venv/bin/python setup_indexes.py  # creates regular + vector + text search indexes

# run (backend :8100 + frontend :5190)
./start.sh                           # or ./run.sh — opens browser, logs to /tmp/mm-garantia-*.log

# smoke test full pipeline (lookup -> checklist -> analisar)
cd backend && ./.venv/bin/python test_http.py

# frontend only
cd frontend && npm install --legacy-peer-deps && npm run dev
```

```bash
# unit tests + lint (backend)
cd backend
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/pytest                   # runs backend/tests/
./.venv/bin/ruff check .
```

`test_http.py` is a separate manual smoke test against a running backend (not part of `pytest`, no auto-discovery — run it explicitly).

`start.sh`/`run.sh` skip starting the backend if port 8100 is already occupied — kill stray uvicorn processes if you need a clean restart. Ports 8100/5190 were picked deliberately to avoid colliding with another PoV that runs on 8000/5173-5174 on the same machine.

## Architecture

**Everything is parameterized by `.env`** (DB name, collection names, index names, model names) — read once by `backend/config.py`, which searches up the directory tree for `.env` so it works whether `.env` lives at repo root or inside `mm-analise-garantia/`. Never hardcode a collection/index/model name; add it to `config.py` + `.env.example` instead.

### MongoDB is the engine for every layer, not just storage

| Layer | Lives in |
|---|---|
| Order lookup | collection `pedidos` |
| Defect checklist catalog | collection `catalogo` |
| Cases + verdict + embedding | collection `chamados` |
| Semantic search | Atlas Vector Search (`$vectorSearch`, index `defeitos_vector_index`) |
| Hybrid search | `$rankFusion` (vector + Atlas Search full-text, index `chamados_text_index`) |
| Live review queue | Change Streams (SSE) — wired into `Revisao.jsx` via `EventSource`, no polling |
| Analytics | Aggregation Pipeline (feeds Atlas Charts) |
| Schema governance | `$jsonSchema` validator on `chamados`/`pedidos` (`validationAction=warn`, applied by `setup_indexes.py`) |

Images/blobs are **never** stored in MongoDB. In the PoV they go to local disk (`backend/media/`, served by FastAPI static files); production swaps `storage.py` for S3 + CDN behind the same `(uri, url)` return contract — don't change that interface.

### Request flow (`POST /api/analisar` in `backend/main.py`)

1. Resolve product from `pedidos` by `numero_pedido` + `sku` → get `categoria`.
2. Normalize uploaded image to JPEG (`Pillow`) — this is deliberate: keeps media_type consistent with bytes and guarantees a format Claude's vision API accepts (avoids 400s from PNG/WebP/mismatched content-type). The same normalized JPEG bytes go to storage, Voyage, and Claude.
3. Build a natural-language `frase` from checklist + description (`defeitos_catalog.compor_frase`).
4. Upload image via `storage.upload_imagem` → `(uri, url)`.
5. Generate a manual multimodal embedding (`voyage.embed_multimodal`, Voyage `voyage-multimodal-3.5`, 1024d) from `frase` + PIL image.
6. Retrieve precedents: `rag.vector_search` (default) or `rag.hybrid_search` (`modo=hybrid`, uses `$rankFusion`), filtered by `{categoria, status: resolvido}`.
7. Get verdict via `llm.analisar_veredito` — Claude with **forced tool use**, so the verdict is structured output, never fragile JSON parsing off free text. `revisao_humana` is always `true`.
8. Insert the full case (including embedding) into `chamados` with `status: em_analise`.

Human review (`POST /api/revisar`) flips `status` to `resolvido` and sets `veredito.revisao_humana=True` — this is what makes a case eligible as a future precedent.

### Error handling convention

All DB calls go through `db.safe_query(...)`, which wraps exceptions into `SafeQueryError(kind, message)`. A single `@app.exception_handler(SafeQueryError)` in `main.py` converts these to a 503 JSON body `{"error": {"kind", "message"}}`, which the frontend renders as a Banner. Raise `SafeQueryError` directly for domain-level failures too (not-found order, bad SKU, missing embedding) — don't invent a separate error path.

### Frontend

React + Vite + LeafyGreen (MongoDB's design system). LeafyGreen has peer-dep conflicts with current React — `npm install` must use `--legacy-peer-deps` (both `start.sh` and `run.sh` already do this). Structure: `src/App.jsx` (tab shell), `src/tabs/` (one component per portal step), `src/api.js` (fetch wrappers), `src/components/`.

### Backend module map

- `main.py` — FastAPI routes only; business logic delegates to the modules below.
- `observability.py` — structured logging (`LOG_JSON=1` for JSON logs) and in-process metrics. `main.py` wires it up: request-id middleware on every response, `GET /api/metrics`. `db.safe_query` logs before mapping every Mongo exception to a `SafeQueryError`.
- `db.py` — Motor client, collection accessors (`pedidos()`, `catalogo()`, `chamados()`), `safe_query`/`SafeQueryError`.
- `rag.py` — `vector_search` / `hybrid_search` against `chamados`.
- `voyage.py` — `embed_multimodal` wrapper around Voyage AI.
- `llm.py` — Claude call with forced tool use, returns structured verdict.
- `storage.py` — image blob storage; swap this file (not its callers) to move from local disk to S3.
- `defeitos_catalog.py` — checklist → natural-language phrase, tipo_defeito derivation.
- `pedidos_data.py`, `seed_data.py`, `seed.py`, `seed_meta.py` — seed data + scripts.
- `setup_indexes.py` — creates all Mongo indexes (regular, vector, text) from `.env` names.
