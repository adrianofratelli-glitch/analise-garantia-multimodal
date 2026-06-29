# Análise de Garantia Multimodal — PoV de referência (MongoDB Atlas)

PoV **vendor-neutra** de **busca multimodal (imagem + texto)** com **MongoDB Atlas
Vector Search**. Mostra um padrão reaproveitável por qualquer caso de uso que
combine **foto + texto** para recuperar casos parecidos e apoiar uma decisão:

> O usuário descreve um problema e envia uma **foto**; a aplicação gera **um único
> vetor multimodal** (imagem + texto), recupera por **`$vectorSearch`** os
> **precedentes** mais parecidos — com **filtros nativos** no mesmo passo — e um
> **modelo de visão** sugere um veredito, **sempre sujeito a revisão humana**.

O domínio do exemplo é **garantia de móveis** (cadeira / colchão / guarda-roupa),
mas é só o *dataset*. Troque o catálogo e os dados de seed pelo seu caso
(sinistros de seguro, inspeção de ativos, controle de qualidade, e-commerce,
diagnóstico visual, etc.) e o resto continua igual.

## Por que MongoDB (o diferencial)

- **Tudo num só documento**: o **vetor**, os **metadados** e as **regras de
  negócio** (categoria, status) vivem no mesmo documento da collection.
- **`$vectorSearch` nativo com filtros**: a busca vetorial e os filtros
  (`categoria`, `status="resolvido"`) rodam **no mesmo passo**, sem sistema de
  busca à parte e **sem mover dados**.
- **Operacional + vetorial juntos**: o chamado em análise é gravado e, após a
  revisão humana, vira precedente para as próximas buscas — no mesmo cluster.

## Componentes pluggáveis (implementação de referência)

A PoV é **agnóstica** a LLM, modelo de embedding e object storage. A
implementação de referência usa os provedores abaixo — **troque pelo que preferir**:

| Papel | Função no fluxo | Referência usada |
| --- | --- | --- |
| **Embedding multimodal** | 1 vetor de 1024 dims a partir de imagem + texto | Voyage `voyage-multimodal-3` |
| **LLM de visão** | veredito a partir da foto + frase + precedentes | Anthropic `claude-opus-4-8` |
| **Object storage** | guarda o binário da imagem (o Mongo guarda só a URI + vetor) | Amazon S3 |

> Importante: o embedding é multimodal e calculado pela **aplicação** (mesmo
> vetor no seed e no runtime) — **não** usamos auto-embedding text-only.
> DB `POC`, collection `chamados`, índice de vetor `chamados_vector`
> (1024 dims, cosine).

## Arquitetura

```
descrever problema → selecionar produto → checklist + relato → foto
   │
   ├─ compor_frase()                 (mesma função no seed e no runtime → vetores comparáveis)
   ├─ persistir imagem (object storage)   (Mongo guarda só a URI + metadados + vetor)
   ├─ embed multimodal (imagem + texto)   (1024 dims, input_type="query")
   ├─ $vectorSearch nativo                 filtro {categoria, status:"resolvido"}
   ├─ veredito do modelo de visão          {classificacao, confianca, justificativa, recomendacao}
   └─ grava chamado status="em_analise"   → revisão humana → status="resolvido"
```

## Estrutura

```
backend/
  defeitos_catalog.py   catálogo de exemplo + compor_frase() + derivar_tipo_defeito()
  seed_data.py          chamados de exemplo (seed) + pedidos de exemplo
  voyage.py             embedding multimodal (imagem + texto)
  s3.py                 object storage → URI + presigned URL
  db.py                 get_db()/get_collection() + safe_query/SafeQueryError
  rag.py                vector_search(query_vector, categoria) → (docs, funnel)
  llm.py                analisar_veredito() — LLM de visão + saída estruturada
  seed.py               popula a collection e IMPRIME o JSON do índice de vetor
  main.py               FastAPI (/api/health, /pedidos, /lookup, /checklist, /analisar, /revisar)
frontend/               React + Vite + LeafyGreen (PT-BR)
seed_images/            imagens de exemplo (placeholders) + gen_placeholders.py
```

## Variáveis de ambiente (`.env`)

Copie `.env.example` para `.env` e preencha (nomes da implementação de referência):

| Variável | Para quê |
| --- | --- |
| `MONGODB_URI` | cluster Atlas (DB `POC`) |
| `ANTHROPIC_API_KEY` | LLM de visão |
| `VOYAGE_API_KEY` | embedding multimodal |
| `S3_BUCKET` / `AWS_REGION` | object storage das imagens |

Credenciais AWS via ambiente padrão do boto3 (`AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY`, e `AWS_SESSION_TOKEN` se forem temporárias).

## Executar no GitHub Codespaces

> Requer rede para o cluster Atlas e para os provedores de LLM/embedding/storage.

1. **Configurar `.env`**
   ```bash
   cp .env.example .env   # preencha as variáveis acima
   ```
2. **Backend — deps**
   ```bash
   python -m venv backend/.venv
   backend/.venv/bin/pip install -r backend/requirements.txt
   ```
3. **Frontend — deps**
   ```bash
   cd frontend && npm install && cd ..
   ```
4. **(opcional) Trocar as imagens de exemplo** — substitua os arquivos em
   `seed_images/` (mesmos nomes-base `cad_01`, `col_01`, `gr_01`, …; aceita
   `.jpg`/`.jpeg`/`.png`). Para regerar os placeholders:
   `backend/.venv/bin/python seed_images/gen_placeholders.py`
5. **Seed** — popula a collection (sobe imagens, gera embeddings) e **imprime o
   JSON do índice de vetor**. Dá para seedar tudo ou só uma categoria:
   ```bash
   cd backend
   ../backend/.venv/bin/python seed.py                 # todas as categorias
   ../backend/.venv/bin/python seed.py --reset cadeira # só uma categoria, base limpa
   cd ..
   ```
6. **Criar o índice de vetor no Atlas** (`POC.chamados`, nome `chamados_vector`).
   Atlas → *Atlas Search* → *Create Search Index* → *JSON Editor* — cole o bloco
   `definition` impresso pelo seed:
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
   O Vite faz proxy de `/api` → `http://localhost:8000`. Abra a porta 5173 e
   siga o fluxo: selecionar pedido → produto → checklist + relato → foto → veredito.

> Atalho dev: `./start.sh` sobe os dois (espera o venv em `backend/.venv`).

## Docker (opcional)

Imagem única (nginx serve o build do front e faz proxy de `/api` pro uvicorn):
```bash
docker build -t analise-garantia-multimodal .
docker run --rm -p 8080:8080 --env-file .env analise-garantia-multimodal
# abra http://localhost:8080
```

## Endpoints

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/api/health` | ping do Atlas + contagens |
| GET | `/api/pedidos` | lista de pedidos (seleção no front) |
| POST | `/api/lookup` | `{numero_pedido}` → produtos do pedido |
| GET | `/api/checklist/{categoria}` | itens de checklist da categoria |
| POST | `/api/analisar` | multipart (foto + dados) → veredito + precedentes + funil |
| POST | `/api/revisar` | `{numero_chamado, resolucao_final}` → `resolvido` |

## Notas

- A **frase** que vira embedding é produzida por `compor_frase()` — a mesma
  função no seed e no runtime, garantindo vetores comparáveis.
- O veredito do modelo é **sugestão** e passa por **revisão humana** antes de o
  chamado virar `resolvido`.
- As imagens em `seed_images/` são **placeholders**. Para uma demo realista,
  troque por fotos reais (mesmos nomes-base). Fotos reais não são versionadas
  (veja `.gitignore`).
