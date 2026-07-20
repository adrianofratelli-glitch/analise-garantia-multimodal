"""FastAPI — Análise de Garantia Multimodal.

Fluxo do portal: pedido -> produto -> checklist+descrição -> foto -> análise.
Caminho B: embedding multimodal MANUAL, imagem em storage local (file://),
$vectorSearch com queryVector pré-computado + filtro {categoria, status:resolvido},
veredito do Claude via tool use (sempre revisao_humana=true).

MongoDB como motor: pedidos, catálogo e chamados são collections; lookup e
checklist LEEM do banco (não mais de dicts hardcoded). Erros -> SafeQueryError -> Banner.
"""

import asyncio
import io
import json
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

import config
import observability
import rag
from db import SafeQueryError, catalogo, chamados, get_client, pedidos, safe_query
from defeitos_catalog import compor_frase, derivar_tipo_defeito
from llm import MODEL, analisar_veredito
from storage import upload_imagem
from voyage import EMBED_DIM, embed_multimodal
from voyage import MODEL as VOYAGE_MODEL

observability.setup_logging()
logger = logging.getLogger("mm_garantia")

app = FastAPI(title="Análise de Garantia Multimodal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5190", "http://127.0.0.1:5190"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_observability(request: Request, call_next):
    """request_id on every response + per-route latency/error counters at /api/metrics."""
    request_id = request.headers.get("x-request-id") or uuid4().hex[:16]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        observability.metrics.observe(request.url.path, 500, (time.perf_counter() - start) * 1000)
        logger.exception("unhandled error request_id=%s path=%s", request_id, request.url.path)
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    observability.metrics.observe(request.url.path, response.status_code, elapsed_ms)
    response.headers["X-Request-Id"] = request_id
    return response


@app.get("/api/metrics")
async def api_metrics():
    """In-process counters: requests/errors/latency per route + business counters."""
    return observability.metrics.snapshot()

# Imagens servidas localmente (PoV). Em prod, trocar storage.py por S3 + CDN.
config.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount(config.MEDIA_URL_PREFIX, StaticFiles(directory=str(config.MEDIA_ROOT)), name="media")

ALLOWED_MEDIA = {"image/jpeg", "image/jpg", "image/png"}


@app.exception_handler(SafeQueryError)
async def safe_query_handler(_: Request, exc: SafeQueryError):
    return JSONResponse(status_code=503, content={"error": {"kind": exc.kind, "message": exc.message}})


def clean(doc):
    if isinstance(doc, list):
        return [clean(d) for d in doc]
    if isinstance(doc, dict):
        return {k: clean(v) for k, v in doc.items()}
    if isinstance(doc, (ObjectId, datetime)):
        return str(doc)
    return doc


@app.get("/api/health")
async def health():
    await safe_query(get_client().admin.command("ping"))
    col = chamados()
    return {
        "ping": "ok",
        "model": MODEL,
        "embedding_model": VOYAGE_MODEL,
        "embedding_dim": EMBED_DIM,
        "db": config.DB_NAME,
        # Um único $group substitui três count_documents (3 scans → 1).
        "counts": await _counts_por_status(col),
    }


async def _counts_por_status(col) -> dict:
    rows = await safe_query(
        col.aggregate(
            [{"$group": {"_id": "$status", "n": {"$sum": 1}}}],
            maxTimeMS=config.MAX_TIME_MS,
        ).to_list(length=20)
    )
    por_status = {r["_id"]: r["n"] for r in rows}
    return {
        "total": sum(por_status.values()),
        "resolvido": por_status.get("resolvido", 0),
        "em_analise": por_status.get("em_analise", 0),
    }


@app.get("/api/pedidos")
async def listar_pedidos():
    cursor = pedidos().find({}, {"_id": 0}, max_time_ms=config.MAX_TIME_MS).sort("numero_pedido", 1)
    docs = await safe_query(cursor.to_list(length=200))
    return {"pedidos": docs}


class LookupBody(BaseModel):
    numero_pedido: str


@app.post("/api/lookup")
async def lookup(body: LookupBody):
    numero = body.numero_pedido.strip().upper()
    doc = await safe_query(pedidos().find_one({"numero_pedido": numero}, {"_id": 0}, max_time_ms=config.MAX_TIME_MS))
    if not doc:
        disponiveis = await safe_query(
            pedidos().distinct("numero_pedido", maxTimeMS=config.MAX_TIME_MS)
        )
        raise SafeQueryError(
            "config",
            f"Pedido {numero} não encontrado. Tente um de: {', '.join(sorted(disponiveis)) or '(seed pendente)'}.",
        )
    return {"numero_pedido": numero, "produtos": doc["produtos"]}


@app.get("/api/checklist/{categoria}")
async def checklist(categoria: str):
    doc = await safe_query(catalogo().find_one({"categoria": categoria}, {"_id": 0}, max_time_ms=config.MAX_TIME_MS))
    if not doc:
        raise SafeQueryError("config", f"Categoria '{categoria}' sem checklist no catálogo.")
    return {"categoria": categoria, "itens": doc["itens"]}


async def _resolver_produto(numero_pedido: str, sku: str) -> dict:
    doc = await safe_query(pedidos().find_one({"numero_pedido": numero_pedido.strip().upper()}, max_time_ms=config.MAX_TIME_MS))
    for p in (doc or {}).get("produtos", []):
        if p["sku"] == sku:
            return p
    raise SafeQueryError("config", f"SKU {sku} não pertence ao pedido {numero_pedido}.")


async def _tabela_catalogo(categoria: str) -> dict:
    doc = await safe_query(catalogo().find_one({"categoria": categoria}, {"_id": 0}, max_time_ms=config.MAX_TIME_MS))
    return {item["id"]: item["tipo"] for item in (doc or {}).get("itens", [])}


async def _ler_e_normalizar(upload: UploadFile) -> tuple[Image.Image, bytes]:
    """Valida, lê e normaliza um UploadFile para JPEG (mesmo contrato da foto principal)."""
    if upload.content_type not in ALLOWED_MEDIA:
        raise SafeQueryError("imagem", f"Formato '{upload.content_type}' não aceito. Envie JPEG ou PNG.")
    imagem_bytes = await upload.read()
    if not imagem_bytes:
        raise SafeQueryError("imagem", "Nenhuma imagem recebida.")
    if len(imagem_bytes) > config.MAX_IMAGE_BYTES:
        mb = config.MAX_IMAGE_BYTES // (1024 * 1024)
        raise SafeQueryError("imagem", f"Imagem maior que o limite de {mb} MB.")
    try:
        pil = Image.open(io.BytesIO(imagem_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise SafeQueryError("imagem", "Arquivo enviado não é uma imagem válida.") from e
    # Normaliza TUDO para JPEG: garante que o media_type bate com os bytes e que o
    # formato é sempre suportado pelo Claude (evita 400 com PNG/WebP/content-type
    # divergente). A mesma imagem normalizada vai pro storage, Voyage e Claude.
    # Thumbnail 1568x1568 primeiro: é o teto que a visão do Claude usa — acima
    # disso a API redimensiona do lado dela cobrando os tokens da imagem cheia.
    pil.thumbnail((1568, 1568))
    _buf = io.BytesIO()
    pil.save(_buf, format="JPEG", quality=90)
    return pil, _buf.getvalue()


@app.post("/api/analisar")
async def analisar(
    imagem: UploadFile,
    numero_pedido: str = Form(...),
    sku: str = Form(...),
    descricao: str = Form(""),
    checklist: list[str] = Form(default=[]),
    modo: str = Form("vector"),  # "vector" (padrão) ou "hybrid" ($rankFusion)
    # Fotos extras, uma por item de checklist marcado — cada uma gera seu próprio
    # embedding multimodal (roda verificar_identidade também) e vai junto da foto
    # principal para o Claude no veredito; não é só evidência guardada.
    fotos_extra: list[UploadFile] = File(default=[]),
    fotos_extra_itens: list[str] = Form(default=[]),
):
    produto = await _resolver_produto(numero_pedido, sku)
    categoria = produto["categoria"]

    if len(fotos_extra) != len(fotos_extra_itens):
        raise SafeQueryError("imagem", "Cada foto extra precisa estar associada a exatamente um item do checklist.")

    pil, imagem_jpeg = await _ler_e_normalizar(imagem)
    media_type = "image/jpeg"

    chamado = {
        "categoria": categoria,
        "produto": {"sku": produto["sku"], "nome": produto["nome"]},
        "checklist": checklist,
        "descricao_cliente": descricao,
    }
    frase = compor_frase(chamado)
    tabela = await _tabela_catalogo(categoria)

    numero_chamado = f"CHM-{datetime.now(UTC).year}-{uuid4().hex[:6].upper()}"
    key = f"chamados/{numero_chamado}/foto.jpg"
    # Upload em task paralela: não bloqueia o caminho crítico (embedding → RAG →
    # veredito); o resultado só é aguardado na montagem da resposta.
    upload_task = asyncio.create_task(
        run_in_threadpool(upload_imagem, imagem_jpeg, key, media_type)
    )

    extras_normalizadas = [await _ler_e_normalizar(f) for f in fotos_extra]
    extras_upload_tasks = [
        asyncio.create_task(
            run_in_threadpool(
                upload_imagem, jpeg_bytes, f"chamados/{numero_chamado}/extra_{i}_{item}.jpg", media_type
            )
        )
        for i, ((_, jpeg_bytes), item) in enumerate(zip(extras_normalizadas, fotos_extra_itens, strict=True))
    ]

    try:
        query_vector = await run_in_threadpool(embed_multimodal, frase, pil, "query")
    except Exception as e:
        upload_task.cancel()
        for t in extras_upload_tasks:
            t.cancel()
        logger.exception("multimodal embedding failed numero_pedido=%s", numero_pedido)
        raise SafeQueryError("embedding", f"Falha ao gerar o embedding multimodal: {str(e)[:160]}") from e

    # Embedding de cada foto extra: mesma frase do chamado (o item já está nela
    # via checklist), contrato idêntico ao da foto principal.
    try:
        extras_vetores = await asyncio.gather(
            *(run_in_threadpool(embed_multimodal, frase, extra_pil, "query") for extra_pil, _ in extras_normalizadas)
        )
    except Exception as e:
        upload_task.cancel()
        for t in extras_upload_tasks:
            t.cancel()
        logger.exception("multimodal embedding (foto extra) failed numero_pedido=%s", numero_pedido)
        raise SafeQueryError("embedding", f"Falha ao gerar o embedding de uma foto extra: {str(e)[:160]}") from e

    # Identidade e precedentes são consultas independentes sobre o mesmo vetor.
    # Identidade roda pra foto principal E pra cada foto extra — o mais restritivo
    # vence (se qualquer foto divergir do SKU, o chamado inteiro fica sinalizado).
    if modo == "hybrid":
        busca = rag.hybrid_search(query_vector, frase, categoria)
    else:
        busca = rag.vector_search(query_vector, categoria)
    identidade_principal, *identidades_extra, (precedentes, funnel) = await asyncio.gather(
        rag.verificar_identidade(query_vector, produto["sku"]),
        *(rag.verificar_identidade(v, produto["sku"]) for v in extras_vetores),
        busca,
    )
    identidade = {
        **identidade_principal,
        "fotos_extra": [
            {"item": item, **ident}
            for item, ident in zip(fotos_extra_itens, identidades_extra, strict=True)
        ],
        "abaixo_threshold": identidade_principal["abaixo_threshold"] or any(i["abaixo_threshold"] for i in identidades_extra),
    }

    try:
        imagens_extra_veredito = [
            (jpeg_bytes, media_type, item)
            for (_, jpeg_bytes), item in zip(extras_normalizadas, fotos_extra_itens, strict=True)
        ]
        veredito = await analisar_veredito(imagem_jpeg, media_type, frase, precedentes, imagens_extra_veredito)
    except Exception as e:
        upload_task.cancel()
        for t in extras_upload_tasks:
            t.cancel()
        logger.exception("Claude verdict call failed numero_pedido=%s", numero_pedido)
        raise SafeQueryError("modelo", f"Falha ao consultar o Claude: {str(e)[:160]}") from e

    try:
        uri, imagem_url = await upload_task
        extras_uploads = await asyncio.gather(*extras_upload_tasks)
    except Exception as e:
        logger.exception("image upload failed numero_chamado=%s", numero_chamado)
        raise SafeQueryError("imagem", f"Falha ao salvar a imagem: {str(e)[:160]}") from e

    fotos_extra_doc = [
        {"item": item, "uri": extra_uri, "url": extra_url}
        for item, (extra_uri, extra_url) in zip(fotos_extra_itens, extras_uploads, strict=True)
    ]

    doc = {
        "numero_chamado": numero_chamado,
        "numero_pedido": numero_pedido.strip().upper(),
        "produto": chamado["produto"],
        "categoria": categoria,
        "tipo_defeito": derivar_tipo_defeito(tabela, checklist),
        "checklist": checklist,
        "descricao_cliente": descricao,
        "frase_analise": frase,
        "imagem_cliente_uri": uri,
        "fotos_extra": fotos_extra_doc,
        "embedding": query_vector,
        "veredito": veredito,
        "identidade_produto": identidade,
        "resolucao_final": None,
        "status": "em_analise",
        "created_at": datetime.now(UTC),
    }
    await safe_query(chamados().insert_one(doc))

    return clean({
        "numero_chamado": numero_chamado,
        "categoria": categoria,
        "produto": chamado["produto"],
        "frase_analise": frase,
        "imagem_url": imagem_url,
        "fotos_extra": fotos_extra_doc,
        "veredito": veredito,
        "identidade": identidade,
        "precedentes": [{k: v for k, v in p.items() if k != "embedding"} for p in precedentes],
        "funnel": funnel,
        "embedding_model": VOYAGE_MODEL,
        "embedding_dim": len(query_vector),
    })


@app.get("/api/chamados/pendentes")
async def chamados_pendentes():
    cursor = chamados().find(
        {"status": "em_analise"}, {"embedding": 0}, max_time_ms=config.MAX_TIME_MS
    ).sort("created_at", -1)
    return clean(await safe_query(cursor.to_list(length=50)))


class RevisarBody(BaseModel):
    numero_chamado: str
    resolucao_final: str


@app.post("/api/revisar")
async def revisar(body: RevisarBody):
    res = await safe_query(
        chamados().update_one(
            {"numero_chamado": body.numero_chamado},
            {"$set": {
                "resolucao_final": body.resolucao_final,
                "status": "resolvido",
                "veredito.revisao_humana": True,
                "revisado_at": datetime.now(UTC),
            }},
        )
    )
    if res.matched_count == 0:
        raise SafeQueryError("config", f"Chamado {body.numero_chamado} não encontrado.")
    doc = await safe_query(
        chamados().find_one({"numero_chamado": body.numero_chamado}, {"embedding": 0}, max_time_ms=config.MAX_TIME_MS)
    )
    return clean(doc)


@app.get("/api/analytics")
async def analytics():
    """Aggregation Pipeline — material para Atlas Charts: distribuição de
    classificações, confiança média e latência média do modelo, por categoria."""
    col = chamados()
    por_classificacao = await safe_query(col.aggregate([
        {"$group": {
            "_id": "$veredito.classificacao",
            "n": {"$sum": 1},
            "confianca_media": {"$avg": "$veredito.confianca"},
            "latencia_media_ms": {"$avg": "$veredito._meta.latency_ms"},
        }},
        {"$sort": {"n": -1}},
    ], maxTimeMS=config.MAX_TIME_MS).to_list(length=20))

    por_categoria = await safe_query(col.aggregate([
        {"$group": {
            "_id": {"categoria": "$categoria", "classificacao": "$veredito.classificacao"},
            "n": {"$sum": 1},
        }},
        {"$sort": {"_id.categoria": 1, "n": -1}},
    ], maxTimeMS=config.MAX_TIME_MS).to_list(length=100))

    return clean({"por_classificacao": por_classificacao, "por_categoria": por_categoria})


@app.get("/api/chamados/stream")
async def chamados_stream():
    """Change Stream (SSE) — empurra novos chamados em_analise em tempo real,
    sem polling. Demonstra real-time operacional nativo do MongoDB."""

    async def _gen():
        # $project no próprio stream: sem ele cada evento carrega o fullDocument
        # inteiro — incluindo o embedding de 1024 floats — pela rede a cada chamado.
        pipeline = [
            {"$match": {"operationType": {"$in": ["insert", "update", "replace"]}}},
            {"$project": {
                "operationType": 1,
                "fullDocument.numero_chamado": 1,
                "fullDocument.categoria": 1,
                "fullDocument.produto": 1,
                "fullDocument.status": 1,
            }},
        ]
        try:
            async with chamados().watch(pipeline, full_document="updateLookup") as stream:
                yield ": stream conectado\n\n"
                async for change in stream:
                    doc = change.get("fullDocument") or {}
                    if doc.get("status") != "em_analise":
                        continue
                    payload = {
                        "numero_chamado": doc.get("numero_chamado"),
                        "categoria": doc.get("categoria"),
                        "produto": doc.get("produto"),
                        "status": doc.get("status"),
                    }
                    yield f"data: {json.dumps(payload, default=str)}\n\n"
        except Exception as e:  # change streams exigem replica set (Atlas tem)
            logger.exception("change stream failed")
            yield f"event: error\ndata: {json.dumps({'message': str(e)[:200]})}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")
