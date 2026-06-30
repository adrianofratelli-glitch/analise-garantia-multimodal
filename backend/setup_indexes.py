"""Cria os índices em madeira_madeira.chamados (+ pedidos/catalogo).

- Regulares: acelera as queries operacionais (status/created_at, lookups).
- Vetorial (Atlas Vector Search): para o $vectorSearch.
- Texto (Atlas Search): para a busca híbrida ($rankFusion).

Tenta criar os índices de busca via pymongo (create_search_index). Se o cluster/
permissão não permitir, imprime o JSON para criar no Atlas UI.

    python setup_indexes.py
"""

import json
import sys

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.operations import SearchIndexModel

import config

VECTOR_DEF = {
    "fields": [
        {"type": "vector", "path": "embedding", "numDimensions": config.EMBEDDING_DIM, "similarity": "cosine"},
        {"type": "filter", "path": "categoria"},
        {"type": "filter", "path": "status"},
    ]
}

TEXT_DEF = {
    "mappings": {
        "dynamic": False,
        "fields": {
            "descricao_cliente": {"type": "string"},
            "frase_analise": {"type": "string"},
            "categoria": {"type": "string"},
            "status": {"type": "string"},
        },
    }
}


def _regular_indexes(db):
    db[config.CHAMADOS_COLL].create_index([("status", ASCENDING), ("created_at", DESCENDING)], name="status_created")
    db[config.CHAMADOS_COLL].create_index([("numero_chamado", ASCENDING)], name="numero_chamado", unique=True)
    db[config.PEDIDOS_COLL].create_index([("numero_pedido", ASCENDING)], name="numero_pedido", unique=True)
    db[config.CATALOGO_COLL].create_index([("categoria", ASCENDING)], name="categoria", unique=True)
    print("✓ índices regulares criados (status_created, numero_chamado, numero_pedido, categoria)")


def _search_index(col, name, definition, kind):
    try:
        col.create_search_index(SearchIndexModel(definition=definition, name=name, type=kind))
        print(f"✓ índice de busca '{name}' ({kind}) criado — building em background no Atlas.")
    except Exception as e:
        msg = str(e).lower()
        if "already exists" in msg or "duplicate" in msg:
            print(f"• índice '{name}' já existe — ok.")
        else:
            print(f"⚠ não foi possível criar '{name}' via código ({type(e).__name__}: {str(e)[:120]}).")
            print(f"  Crie no Atlas UI ({config.DB_NAME}.{config.CHAMADOS_COLL}, tipo {kind}, nome '{name}'):")
            print(json.dumps(definition, indent=2, ensure_ascii=False))


def main():
    if not config.MONGODB_URI:
        sys.exit("MONGODB_URI não definida — preencha o .env.")
    c = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=10_000)
    c.admin.command("ping")
    db = c[config.DB_NAME]

    _regular_indexes(db)
    _search_index(db[config.CHAMADOS_COLL], config.VECTOR_INDEX, VECTOR_DEF, "vectorSearch")
    _search_index(db[config.CHAMADOS_COLL], config.TEXT_INDEX, TEXT_DEF, "search")


if __name__ == "__main__":
    main()
