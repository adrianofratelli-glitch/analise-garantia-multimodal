# MM Análise de Garantia — PoV (MadeiraMadeira)

Análise de chamados de garantia com **embedding multimodal** (foto + texto) +
**$vectorSearch** no MongoDB Atlas + **veredito com visão** do Claude.

O analista informa o pedido, escolhe o produto, marca os defeitos no checklist,
descreve o problema e envia uma foto. A app compõe uma frase, gera um embedding
multimodal (texto + imagem) com a **Voyage**, recupera **precedentes resolvidos**
parecidos via `$vectorSearch`, e o **Claude** emite um veredito (procedente /
improcedente / inconclusivo) **sujeito a revisão humana**.

## Arquitetura (Caminho B — embedding multimodal MANUAL)

```
pedido → produto → checklist+relato → foto
   │
   ├─ compor_frase()                      (defeitos_catalog — idêntico no seed e no runtime)
   ├─ upload da foto → S3 (boto3)         (Mongo guarda só a URI s3:// + metadados + vetor)
   ├─ embed_multimodal(texto+imagem)      (voyage-multimodal-3, 1024d, input_type="query")
   ├─ $vectorSearch (queryVector pré-computado)   filtro {categoria, status:"resolvido"}
   ├─ Claude opus-4-8 (visão)             veredito {classificacao, confianca, justificativa, recomendacao}
   └─ grava chamado status="em_analise"  → revisão humana → status="resolvido"
```

- **NÃO** usamos autoEmbed do Atlas (é text-only e não enxerga a imagem). O
  embedding é multimodal e calculado pela aplicação, no seed e no runtime.
- DB `POC`, collection `chamados`, índice de vetor `chamados_vector` (1024 dims, cosine).

## Estrutura

```
backend/
  defeitos_catalog.py   PRODUTOS, CATALOGO_DEFEITOS, compor_frase(), derivar_tipo_defeito()
  seed_data.py          CHAMADOS_SEED (15) + PEDIDOS_MOCK
  voyage.py             cliente Voyage + embed_multimodal()
  s3.py                 upload boto3 → URI s3:// + presigned URL
  db.py                 get_db()/get_collection() + safe_query/SafeQueryError
  rag.py                vector_search(query_vector, categoria) → (docs, funnel)
  llm.py                analisar_veredito() — Claude com visão + structured output
  seed.py               popula POC.chamados e IMPRIME o JSON do índice
  main.py               FastAPI (/api/health, /lookup, /checklist, /analisar, /revisar)
frontend/               React + Vite + LeafyGreen (PT-BR)
seed_images/            cad_01..05, col_01..05, gr_01..05 (placeholders) + gen_placeholders.py
```

## Variáveis de ambiente (`.env`)

Copie `.env.example` para `.env` e preencha:

| Variável            | Para quê                                  |
| ------------------- | ----------------------------------------- |
| `MONGODB_URI`       | cluster Atlas (DB `POC`)                  |
| `ANTHROPIC_API_KEY` | veredito com visão (`claude-opus-4-8`)    |
| `VOYAGE_API_KEY`    | embedding multimodal (`voyage-multimodal-3`) |
| `S3_BUCKET`         | bucket S3 das imagens                     |
| `AWS_REGION`        | região do bucket                          |

Credenciais AWS via ambiente padrão do boto3 (`AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY`, ou role).

## Executar no GitHub Codespaces

> Requer rede para Atlas, Voyage, S3 e Anthropic.

1. **Configurar `.env`**
   ```bash
   cp .env.example .env   # preencha MONGODB_URI, ANTHROPIC_API_KEY, VOYAGE_API_KEY, S3_BUCKET, AWS_REGION
   ```

2. **Backend — instalar deps**
   ```bash
   python -m venv backend/.venv
   backend/.venv/bin/pip install -r backend/requirements.txt
   ```

3. **Frontend — instalar deps**
   ```bash
   cd frontend && npm install && cd ..
   ```

4. **(opcional) Regerar as fotos placeholder** — já versionadas em `seed_images/`.
   Para trocar por fotos reais, mantenha os mesmos nomes (`cad_01.png`, …).
   ```bash
   backend/.venv/bin/python seed_images/gen_placeholders.py
   ```

5. **Seed** — popula `POC.chamados` (sobe imagens pro S3, gera embeddings) e
   **imprime o JSON do índice** a criar no Atlas:
   ```bash
   cd backend && ../backend/.venv/bin/python seed.py && cd ..
   ```

6. **Criar o índice de vetor no Atlas** (`POC.chamados`, nome `chamados_vector`).
   Atlas UI → *Atlas Search* → *Create Search Index* → *JSON Editor*, ou via API.
   O `seed.py` imprime exatamente este JSON:
   ```json
   {
     "fields": [
       { "type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine" },
       { "type": "filter", "path": "categoria" },
       { "type": "filter", "path": "status" }
     ]
   }
   ```

7. **Subir backend (porta 8000)**
   ```bash
   cd backend && ../backend/.venv/bin/uvicorn main:app --port 8000
   ```

8. **Subir frontend (porta 5173)** — em outro terminal
   ```bash
   cd frontend && npm run dev
   ```
   O Vite faz proxy de `/api` → `http://localhost:8000`. Abra a porta 5173.

> Atalho dev: `./start.sh` sobe os dois (espera o venv em `backend/.venv`).

## Docker (opcional)

Imagem única (nginx serve o build do front e faz proxy de `/api` pro uvicorn):
```bash
docker build -t mm-analise-garantia .
docker run --rm -p 8080:8080 --env-file .env mm-analise-garantia
# abra http://localhost:8080
```

## Endpoints

| Método | Rota                      | Descrição                                            |
| ------ | ------------------------- | ---------------------------------------------------- |
| GET    | `/api/health`             | ping do Atlas + contagens                            |
| POST   | `/api/lookup`             | `{numero_pedido}` → produtos do pedido               |
| GET    | `/api/checklist/{categoria}` | itens de checklist da categoria                   |
| POST   | `/api/analisar`           | multipart (foto + dados) → veredito + precedentes + funil |
| POST   | `/api/revisar`            | `{numero_chamado, resolucao_final}` → `resolvido`    |

## Notas

- A **frase** usada para gerar o embedding é produzida por `compor_frase()` em
  `defeitos_catalog.py` — a mesma função no seed e no runtime, garantindo vetores
  comparáveis.
- O veredito do Claude é **sugestão** e sempre passa pela **tela de revisão humana**
  antes de o chamado virar `resolvido`.
- As imagens em `seed_images/` são **placeholders**. Para uma demo realista,
  substitua por fotos reais dos produtos (mesmos nomes de arquivo).
