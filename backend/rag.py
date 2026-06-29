"""$vectorSearch sobre POC.chamados (índice 'chamados_vector').

O queryVector é PRÉ-COMPUTADO pela aplicação (Voyage multimodal) e passado
pronto no pipeline — não usamos autoEmbed. Filtramos por categoria e só
trazemos precedentes já resolvidos (status="resolvido").

Devolve (docs, funnel): `funnel` carrega os números reais de cada etapa da
recuperação, para o PipelineSteps.jsx mostrar o afunilamento candidatos → top-k.
"""

from db import MAX_TIME_MS, VECTOR_INDEX, get_collection, safe_query

NUM_CANDIDATES = 100
LIMIT = 5


async def vector_search(query_vector: list[float], categoria: str) -> tuple[list[dict], dict]:
    """Recupera os precedentes mais parecidos com a foto+frase do chamado atual.

    Args:
        query_vector: vetor 1024-d pré-computado (Voyage, input_type="query").
        categoria: 'cadeira' | 'colchao' | 'guarda_roupa' — filtro do vectorSearch.

    Returns:
        (docs, funnel)
    """
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": NUM_CANDIDATES,
                "limit": LIMIT,
                "filter": {"categoria": categoria, "status": "resolvido"},
            }
        },
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {
            "$project": {
                "embedding": 0,  # não devolve o vetor (1024 floats) pro frontend
            }
        },
    ]

    cursor = get_collection().aggregate(pipeline, maxTimeMS=MAX_TIME_MS)
    docs = await safe_query(cursor.to_list(length=LIMIT))

    for d in docs:
        d["_id"] = str(d["_id"])

    funnel = {
        "num_candidates": NUM_CANDIDATES,
        "limit": LIMIT,
        "filtro": {"categoria": categoria, "status": "resolvido"},
        "recuperados": len(docs),
        "melhor_score": round(docs[0]["score"], 4) if docs else None,
    }
    return docs, funnel
