"""Recuperação de precedentes sobre a collection de chamados.

- vector_search: $vectorSearch puro (usado pelo /api/analisar). queryVector é
  PRÉ-COMPUTADO (Caminho B). Pré-filtro {categoria, status:"resolvido"}.
- hybrid_search: $rankFusion combinando vetorial + Atlas Search full-text (demo
  da força do Atlas). Degrada com graça se o cluster não suportar $rankFusion.

Nada aqui cria índice nem modifica documentos.
"""

import config
from db import SafeQueryError, catalogo_fotos, chamados, safe_query

NUM_CANDIDATES = 100
LIMIT = 5
_PROJECT = {"embedding": 0}

# Abaixo disso, a foto do cliente não se parece o suficiente com nenhuma das
# fotos de referência do SKU — sinal de produto errado/divergente, não de
# defeito (embedding multimodal mede semelhança semântica, não diff de pixel).
IDENTIDADE_THRESHOLD = 0.55


async def vector_search(query_vector: list[float], categoria: str) -> tuple[list[dict], dict]:
    """Retorna (docs, funnel). funnel carrega os números de cada estágio para o
    PipelineSteps.jsx mostrar o afunilamento candidatos → contexto."""
    pipeline = [
        {
            "$vectorSearch": {
                "index": config.VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": NUM_CANDIDATES,
                "limit": LIMIT,
                "filter": {"categoria": categoria, "status": "resolvido"},
            }
        },
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": _PROJECT},
    ]
    cursor = chamados().aggregate(pipeline, maxTimeMS=config.MAX_TIME_MS)
    docs = await safe_query(cursor.to_list(length=LIMIT))
    for d in docs:
        d["_id"] = str(d["_id"])
    funnel = {
        "modo": "vector",
        "num_candidates": NUM_CANDIDATES,
        "limit": LIMIT,
        "filtro": {"categoria": categoria, "status": "resolvido"},
        "retrieved": len(docs),
    }
    return docs, funnel


async def verificar_identidade(query_vector: list[float], sku: str) -> dict:
    """$vectorSearch da foto do cliente contra as fotos de referência do SKU
    (catalogo_fotos) — responde "essa foto é do produto certo?", não "tem
    defeito?" (isso continua sendo papel do Claude com o precedente histórico).

    Retorna {sku, score, fotos_comparadas, abaixo_threshold}. Se o SKU não tem
    fotos de referência seedadas, retorna score=None (não bloqueia o fluxo).
    """
    pipeline = [
        {
            "$vectorSearch": {
                "index": config.CATALOGO_FOTOS_VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": 20,
                "limit": 4,
                "filter": {"sku": sku},
            }
        },
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedding": 0}},
    ]
    cursor = catalogo_fotos().aggregate(pipeline, maxTimeMS=config.MAX_TIME_MS)
    docs = await safe_query(cursor.to_list(length=4))
    if not docs:
        return {"sku": sku, "score": None, "fotos_comparadas": 0, "abaixo_threshold": False}
    melhor = max(d["score"] for d in docs)
    return {
        "sku": sku,
        "score": melhor,
        "fotos_comparadas": len(docs),
        "abaixo_threshold": melhor < IDENTIDADE_THRESHOLD,
    }


async def hybrid_search(query_vector: list[float], texto: str, categoria: str) -> tuple[list[dict], dict]:
    """Busca híbrida via $rankFusion (vetorial + full-text BM25), fundindo os dois
    rankings. Cai para vector_search se o cluster não tiver $rankFusion."""
    pipeline = [
        {
            "$rankFusion": {
                "input": {
                    "pipelines": {
                        "vetorial": [
                            {
                                "$vectorSearch": {
                                    "index": config.VECTOR_INDEX,
                                    "path": "embedding",
                                    "queryVector": query_vector,
                                    "numCandidates": NUM_CANDIDATES,
                                    "limit": LIMIT,
                                    "filter": {"categoria": categoria, "status": "resolvido"},
                                }
                            }
                        ],
                        "textual": [
                            {
                                "$search": {
                                    "index": config.TEXT_INDEX,
                                    "compound": {
                                        "must": [{"text": {"query": texto, "path": ["descricao_cliente", "frase_analise"]}}],
                                        # categoria/status são enums indexados como "token" (exact match),
                                        # não texto analisado — evita falso-positivo/negativo por stemming.
                                        "filter": [
                                            {"equals": {"path": "categoria", "value": categoria}},
                                            {"equals": {"path": "status", "value": "resolvido"}},
                                        ],
                                    },
                                }
                            },
                            {"$limit": LIMIT},
                        ],
                    }
                },
                "combination": {"weights": {"vetorial": 0.7, "textual": 0.3}},
            }
        },
        {"$limit": LIMIT},
        {"$addFields": {"score": {"$meta": "score"}}},
        {"$project": _PROJECT},
    ]
    cursor = chamados().aggregate(pipeline, maxTimeMS=config.MAX_TIME_MS)
    try:
        docs = await safe_query(cursor.to_list(length=LIMIT))
    except SafeQueryError as e:
        # Só degrada pra vetorial quando a causa é ausência de suporte/índice —
        # qualquer outro erro (conexão, timeout) sobe normal pro Banner de erro.
        msg = e.message.lower()
        if e.kind in ("search", "indice") or "rankfusion" in msg or "unrecognized pipeline stage" in msg:
            docs, funnel = await vector_search(query_vector, categoria)
            funnel["modo"] = "vector_fallback"
            funnel["fallback_motivo"] = e.message[:160]
            return docs, funnel
        raise
    for d in docs:
        d["_id"] = str(d["_id"])
    funnel = {
        "modo": "hybrid",
        "limit": LIMIT,
        "num_candidates": NUM_CANDIDATES,
        "retrieved": len(docs),
        "pesos": {"vetorial": 0.7, "textual": 0.3},
    }
    return docs, funnel
