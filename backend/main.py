"""FastAPI — Análise de Garantia Multimodal (PoV de referência).

PoV vendor-neutra de busca multimodal (imagem + texto) no MongoDB Atlas.
O domínio (garantia de móveis) é só o dataset de exemplo — troque pelo seu caso.

Fluxo do analista:
  pedido -> produto -> checklist+descrição -> upload da foto -> veredito.

Endpoints (sob /api, proxied pelo nginx/vite):
  GET  /api/health
  POST /api/lookup              {numero_pedido} -> produtos do pedido (PEDIDOS_MOCK)
  GET  /api/checklist/{categoria} -> itens de CATALOGO_DEFEITOS
  POST /api/analisar            (multipart) -> compor_frase -> S3 -> embed query
                                -> $vectorSearch -> Claude -> grava em_analise
                                -> veredito + precedentes + funnel
  POST /api/revisar             {numero_chamado, resolucao_final} -> resolvido

Erros operacionais sobem como SafeQueryError -> 503 {error:{kind,message}} -> Banner.
"""

import base64
import io
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel

import rag
import s3
import voyage
from db import MAX_TIME_MS, VECTOR_INDEX, get_client, get_collection, safe_query
from defeitos_catalog import (
    CATALOGO_DEFEITOS,
    PRODUTOS,
    categoria_do_sku,
    compor_frase,
    derivar_tipo_defeito,
    nome_do_produto,
)
from llm import analisar_veredito
from seed_data import PEDIDOS_MOCK

app = FastAPI(title="Análise de Garantia Multimodal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception):
    # SafeQueryError tem .kind/.message; demais viram erro genérico amigável.
    kind = getattr(exc, "kind", "erro")
    message = getattr(exc, "message", str(exc))
    return JSONResponse(status_code=503, content={"error": {"kind": kind, "message": message}})


def clean(doc):
    """ObjectId/datetime -> string para JSON."""
    if isinstance(doc, list):
        return [clean(d) for d in doc]
    if isinstance(doc, dict):
        return {k: clean(v) for k, v in doc.items()}
    if isinstance(doc, (ObjectId, datetime)):
        return str(doc)
    return doc


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/api/health")
async def health():
    await safe_query(get_client().admin.command("ping"))
    coll = get_collection()
    total = await safe_query(coll.count_documents({}, maxTimeMS=MAX_TIME_MS))
    resolvidos = await safe_query(
        coll.count_documents({"status": "resolvido"}, maxTimeMS=MAX_TIME_MS)
    )
    return {
        "ping": "ok",
        "counts": {"chamados": total, "resolvidos": resolvidos},
        "vector_index": VECTOR_INDEX,
        "dims": voyage.EMBED_DIMS,
    }


# --------------------------------------------------------------------------- #
# Lista de pedidos (para seleção no front — sem digitação)
# --------------------------------------------------------------------------- #
@app.get("/api/pedidos")
async def pedidos():
    return {
        "pedidos": [
            {"numero_pedido": p["numero_pedido"], "cliente": p["cliente"], "data": p["data"]}
            for p in PEDIDOS_MOCK
        ]
    }


# --------------------------------------------------------------------------- #
# Lookup do pedido -> produtos
# --------------------------------------------------------------------------- #
class LookupBody(BaseModel):
    numero_pedido: str


@app.post("/api/lookup")
async def lookup(body: LookupBody):
    numero = body.numero_pedido.strip().upper()
    pedido = next((p for p in PEDIDOS_MOCK if p["numero_pedido"].upper() == numero), None)
    if not pedido:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "kind": "pedido",
                    "message": f"Pedido '{body.numero_pedido}' não encontrado. "
                    f"Tente um destes: {', '.join(p['numero_pedido'] for p in PEDIDOS_MOCK)}.",
                }
            },
        )
    produtos = [
        {
            "sku": sku,
            "nome": nome_do_produto(sku),
            "categoria": categoria_do_sku(sku),
        }
        for sku in pedido["itens"]
    ]
    return {
        "numero_pedido": pedido["numero_pedido"],
        "cliente": pedido["cliente"],
        "data": pedido["data"],
        "produtos": produtos,
    }


# --------------------------------------------------------------------------- #
# Checklist por categoria
# --------------------------------------------------------------------------- #
@app.get("/api/checklist/{categoria}")
async def checklist(categoria: str):
    itens = CATALOGO_DEFEITOS.get(categoria)
    if itens is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"kind": "categoria", "message": f"Categoria '{categoria}' desconhecida."}},
        )
    return {"categoria": categoria, "itens": itens}


# --------------------------------------------------------------------------- #
# Análise (multipart): foto + dados -> veredito + precedentes + funnel
# --------------------------------------------------------------------------- #
@app.post("/api/analisar")
async def analisar(
    imagem: UploadFile = File(...),
    numero_pedido: str = Form(...),
    sku: str = Form(...),
    checklist: list[str] = Form(default=[]),
    descricao: str = Form(default=""),
):
    if sku not in PRODUTOS:
        return JSONResponse(
            status_code=400,
            content={"error": {"kind": "sku", "message": f"SKU '{sku}' não pertence ao catálogo."}},
        )

    categoria = categoria_do_sku(sku)
    media_type = imagem.content_type or "image/png"
    imagem_bytes = await imagem.read()

    # 1. frase de análise (mesma função do seed -> embeddings comparáveis)
    frase = compor_frase(sku, checklist, descricao)

    # 2. persiste a foto no object storage (o Mongo guarda só a URI + metadados)
    up = s3.upload_bytes(imagem_bytes, imagem.filename or "upload.png", prefixo="chamados")
    # devolve a imagem ao front como data-URI (não expõe a URL/origem do storage)
    imagem_data_uri = f"data:{media_type};base64,{base64.standard_b64encode(imagem_bytes).decode()}"

    # 3. embedding multimodal da QUERY (texto + imagem), input_type="query"
    pil = Image.open(io.BytesIO(imagem_bytes)).convert("RGB")
    query_vector = voyage.embed_multimodal(frase, pil, input_type="query")

    # 4. $vectorSearch -> precedentes resolvidos da mesma categoria
    precedentes, funnel = await rag.vector_search(query_vector, categoria)

    # 5. Claude (visão) emite o veredito com base na foto + frase + precedentes
    veredito = await analisar_veredito(imagem_bytes, media_type, frase, precedentes)

    # 6. grava o chamado em análise (já com embedding, para virar precedente após revisão)
    now = datetime.now(timezone.utc)
    numero_chamado = f"CH-{int(now.timestamp())}"
    doc = {
        "numero_chamado": numero_chamado,
        "numero_pedido": numero_pedido,
        "sku": sku,
        "nome_produto": nome_do_produto(sku),
        "categoria": categoria,
        "checklist": checklist,
        "descricao": descricao,
        "frase_analise": frase,
        "tipo_defeito": derivar_tipo_defeito(sku, checklist),
        "imagem_uri": up["uri"],
        "status": "em_analise",
        "veredito": veredito,
        "origem": "runtime",
        "created_at": now,
        "embedding": query_vector,
    }
    await safe_query(get_collection().insert_one(doc))

    return clean(
        {
            "numero_chamado": numero_chamado,
            "categoria": categoria,
            "frase_analise": frase,
            "imagem_url": imagem_data_uri,
            "veredito": veredito,
            "precedentes": precedentes,
            "funnel": funnel,
        }
    )


# --------------------------------------------------------------------------- #
# Revisão humana -> resolve o chamado
# --------------------------------------------------------------------------- #
class RevisarBody(BaseModel):
    numero_chamado: str
    resolucao_final: str


@app.post("/api/revisar")
async def revisar(body: RevisarBody):
    res = await safe_query(
        get_collection().update_one(
            {"numero_chamado": body.numero_chamado},
            {
                "$set": {
                    "status": "resolvido",
                    "resolucao_final": body.resolucao_final,
                    "resolvido_at": datetime.now(timezone.utc),
                }
            },
        )
    )
    if res.matched_count == 0:
        return JSONResponse(
            status_code=404,
            content={"error": {"kind": "chamado", "message": f"Chamado '{body.numero_chamado}' não encontrado."}},
        )
    doc = await safe_query(
        get_collection().find_one({"numero_chamado": body.numero_chamado}, max_time_ms=MAX_TIME_MS)
    )
    doc.pop("embedding", None)
    return clean({"numero_chamado": body.numero_chamado, "status": "resolvido", "chamado": doc})
