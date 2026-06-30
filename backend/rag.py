"""Recuperação de precedentes sobre a collection de chamados.

- vector_search: $vectorSearch puro (usado pelo /api/analisar). queryVector é
  PRÉ-COMPUTADO (Caminho B). Pré-filtro {categoria, status:"resolvido"}.
- hybrid_search: $rankFusion combinando vetorial + Atlas Search full-text (demo
  da força do Atlas). Degrada com graça se o cluster não suportar $rankFusion.

Nada aqui cria índice nem modifica documentos.
"""

import config
from db import chamados, safe_query

NUM_CANDIDATES = 100
LIMIT = 5
_PROJECT = {"embedding": 0}


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
                                        "filter": [
                                            {"text": {"query": categoria, "path": "categoria"}},
                                            {"text": {"query": "resolvido", "path": "status"}},
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
    try:
        cursor = chamados().aggregate(pipeline, maxTimeMS=config.MAX_TIME_MS)
        docs = await cursor.to_list(length=LIMIT)
        for d in docs:
            d["_id"] = str(d["_id"])
        funnel = {"modo": "hybrid", "limit": LIMIT, "retrieved": len(docs),
                  "pesos": {"vetorial": 0.7, "textual": 0.3}}
        return docs, funnel
    except Exception:
        # $rankFusion (Mongo 8.1+) ou índice de texto ausente — cai para vetorial.
        docs, funnel = await vector_search(query_vector, categoria)
        funnel["modo"] = "vector_fallback"
        return docs, funnel
