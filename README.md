# Multimodal Warranty Analysis — Reference PoV (MongoDB Atlas)

> The application UI runs in **Portuguese** (pt-BR) for the demo. This README is
> in English so the project is easy to browse on GitHub.

A **vendor-neutral** proof-of-value for **multimodal (image + text) search** with
**MongoDB Atlas Vector Search**. It shows a pattern any use case can reuse when it
combines a **photo + text** to retrieve similar past cases and support a decision:

> A user describes a problem and uploads a **photo**; the app builds **a single
> multimodal vector** (image + text), retrieves the most similar **precedents**
> via **`$vectorSearch`** — with **native filters** in the same stage — and a
> **vision LLM** suggests a verdict, always **subject to human review**.

The example domain is **furniture warranty** (chair / mattress / wardrobe), but
that's just the dataset. Swap the catalog and seed data for your own case
(insurance claims, asset inspection, quality control, e-commerce, visual
diagnostics, etc.) and the rest stays the same.

## Why MongoDB (the differentiator)

- **Everything in one document**: the **vector**, the **metadata** and the
  **business rules** (category, status) live in the same collection document.
- **Native `$vectorSearch` with filters**: vector search and the filters
  (category, `status="resolvido"`) run **in the same stage**, with no separate
  search system and **without moving data**.
- **Operational + vector together**: the in-review case is stored and, after
  human review, becomes a precedent for future searches — in the same cluster.

## Pluggable components (reference implementation)

The PoV is **agnostic** to the LLM, the embedding model and the object store.
The reference implementation uses concrete providers (visible in
`backend/requirements.txt`) — **swap them for your own**:

| Role | Function in the flow | Configurable in |
| --- | --- | --- |
| **Multimodal embedding** | 1 vector of 1024 dims from image + text | `backend/voyage.py` |
| **Vision LLM** | verdict from photo + text + precedents | `backend/llm.py` (`MODEL`) |
| **Object storage** | holds the image binary (Mongo keeps only the URI + vector) — **optional** | `backend/s3.py` |

> The embedding is multimodal and computed by the **application** (same vector at
> seed and runtime) — we do **not** use text-only auto-embedding.
> DB `POC`, collection `chamados`, vector index `chamados_vector` (1024 dims, cosine).

## Architecture

```
order -> product -> checklist + report -> photo
   |
   |- compor_frase()                   (same function at seed and runtime -> comparable vectors)
   |- persist image (object storage)   (Mongo keeps only the URI + metadata + vector; optional)
   |- multimodal embedding (image + text)  (1024 dims, input_type="query")
   |- native $vectorSearch                  filter {categoria, status:"resolvido"}
   |- vision LLM verdict                     {classificacao, confianca, justificativa, recomendacao}
   |- store case status="em_analise"   -> human review -> status="resolvido"
```

## Layout

```
backend/
  defeitos_catalog.py  example catalog + compor_frase() + derivar_tipo_defeito()
  seed_data.py         example cases (seed) + example orders
  voyage.py            multimodal embedding (image + text)
  s3.py                object storage -> URI + presigned URL (optional)
  db.py                get_db()/get_collection() + safe_query/SafeQueryError
  rag.py               vector_search(query_vector, categoria) -> (docs, funnel)
  llm.py               analisar_veredito() — vision LLM + structured output
  seed.py              populates the collection and PRINTS the vector index JSON
  main.py              FastAPI (/api/health, /pedidos, /lookup, /checklist, /analisar, /revisar)
frontend/              React + Vite + LeafyGreen (UI in pt-BR)
seed_images/           example images (placeholders) + gen_placeholders.py
```

## Environment variables (`.env`)

Copy `.env.example` to `.env` and fill it in:

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | Atlas cluster (DB `POC`) |
| `ANTHROPIC_API_KEY` | vision LLM |
| `VOYAGE_API_KEY` | multimodal embedding |
| `S3_BUCKET` / `AWS_REGION` | object storage for the images (optional) |

AWS credentials via the standard boto3 environment (`AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` for temporary credentials).
Object storage is optional: leave `S3_BUCKET` unset and the analysis still runs
(the image is returned inline and `$vectorSearch` works normally).

## Run on GitHub Codespaces

> Requires network access to the Atlas cluster and the LLM/embedding providers.

### One command

After filling in `.env`, a single idempotent script prepares whatever is missing
(venv, deps) and starts both servers:

```bash
./run.sh --seed   # first run: also seeds POC.chamados and prints the vector-index JSON
./run.sh          # subsequent runs: just starts backend (:8000) + frontend (:5173)
```

On the first `--seed` run, create the `chamados_vector` index in Atlas with the
JSON the seed prints (one time only — the index persists in Atlas). Then open
port 5173.

The detailed, step-by-step version is below.

### Step by step

1. **Configure `.env`**
   ```bash
   cp .env.example .env   # fill in the variables above
   ```
2. **Backend — install deps**
   ```bash
   python -m venv backend/.venv
   backend/.venv/bin/pip install -r backend/requirements.txt
   ```
3. **Frontend — install deps**
   ```bash
   cd frontend && npm install && cd ..
   ```
4. **(optional) Replace the example images** — swap the files in `seed_images/`
   (same base names `cad_01`, `col_01`, `gr_01`, …; `.jpg`/`.jpeg`/`.png`
   accepted). To regenerate placeholders:
   `backend/.venv/bin/python seed_images/gen_placeholders.py`
5. **Seed** — populates the collection (uploads images, generates embeddings)
   and **prints the vector index JSON**. Seed everything or just one category
   (`cadeira`, `colchao`, `guarda_roupa`):
   ```bash
   cd backend
   ../backend/.venv/bin/python seed.py                  # all categories
   ../backend/.venv/bin/python seed.py --reset cadeira  # one category, clean base
   cd ..
   ```
6. **Create the vector index in Atlas** (`POC.chamados`, name `chamados_vector`).
   Atlas -> *Atlas Search* -> *Create Search Index* -> *JSON Editor* — paste the
   `definition` block printed by the seed:
   ```json
   {
     "fields": [
       { "type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine" },
       { "type": "filter", "path": "categoria" },
       { "type": "filter", "path": "status" }
     ]
   }
   ```
7. **Start the backend (port 8000)**
   ```bash
   cd backend && ../backend/.venv/bin/uvicorn main:app --port 8000
   ```
8. **Start the frontend (port 5173)** — in another terminal
   ```bash
   cd frontend && npm run dev
   ```
   Vite proxies `/api` -> `http://localhost:8000`. Open port 5173 and follow the
   flow: select order -> product -> checklist + report -> photo -> verdict.

> Dev shortcut: `./run.sh` does all of the above in one command (see *One command*
> at the top of this section). `./start.sh` only starts the two servers.

## Docker (optional)

Single image (nginx serves the frontend build and proxies `/api` to uvicorn):
```bash
docker build -t warranty-analysis .
docker run --rm -p 8080:8080 --env-file .env warranty-analysis
# open http://localhost:8080
```

## Endpoints

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/health` | Atlas ping + counts |
| GET | `/api/pedidos` | list of orders (for selection in the UI) |
| POST | `/api/lookup` | `{numero_pedido}` -> products of the order |
| GET | `/api/checklist/{categoria}` | checklist items for the category |
| POST | `/api/analisar` | multipart (photo + data) -> verdict + precedents + funnel |
| POST | `/api/revisar` | `{numero_chamado, resolucao_final}` -> `resolvido` |

## Notes

- The text that becomes the embedding is produced by `compor_frase()` — the same
  function at seed and runtime, guaranteeing comparable vectors.
- The LLM verdict is a **suggestion** and goes through **human review** before
  the case becomes `resolvido`.
- The images in `seed_images/` are **placeholders**. For a realistic demo, swap
  them for real photos (same base names). Real photos are not versioned (see
  `.gitignore`).
