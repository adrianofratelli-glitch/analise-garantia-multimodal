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
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

import config

# $jsonSchema — governance nativa do MongoDB: mesmo sendo schemaless por
# padrão, o Atlas valida forma/tipo de documento no servidor sem precisar de
# camada externa (ORM/Zod/etc). validationAction="warn" pra não travar a demo
# se um seed antigo não bater 100% — mas o campo aparece em db.getCollectionInfos().
CHAMADOS_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["numero_chamado", "categoria", "status", "veredito", "embedding"],
        "properties": {
            "numero_chamado": {"bsonType": "string"},
            "categoria": {"bsonType": "string"},
            "status": {"enum": ["em_analise", "resolvido"]},
            "embedding": {
                "bsonType": "array",
                "minItems": config.EMBEDDING_DIM,
                "maxItems": config.EMBEDDING_DIM,
                "items": {"bsonType": "double"},
            },
            "veredito": {
                "bsonType": "object",
                "required": ["classificacao", "confianca", "revisao_humana"],
                "properties": {
                    "classificacao": {
                        "enum": ["defeito_fabrica", "defeito_transporte", "mau_uso", "inconclusivo"]
                    },
                    "confianca": {"bsonType": ["double", "int"], "minimum": 0, "maximum": 1},
                    "revisao_humana": {"bsonType": "bool"},
                },
            },
        },
    }
}

PEDIDOS_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["numero_pedido", "produtos"],
        "properties": {
            "numero_pedido": {"bsonType": "string"},
            "produtos": {"bsonType": "array"},
        },
    }
}

VECTOR_DEF = {
    "fields": [
        {"type": "vector", "path": "embedding", "numDimensions": config.EMBEDDING_DIM, "similarity": "cosine"},
        {"type": "filter", "path": "categoria"},
        {"type": "filter", "path": "status"},
    ]
}

CATALOGO_FOTOS_VECTOR_DEF = {
    "fields": [
        {"type": "vector", "path": "embedding", "numDimensions": config.EMBEDDING_DIM, "similarity": "cosine"},
        {"type": "filter", "path": "sku"},
    ]
}

TEXT_DEF = {
    "mappings": {
        "dynamic": False,
        "fields": {
            "descricao_cliente": {"type": "string"},
            "frase_analise": {"type": "string"},
            # token, não string: categoria/status são enums — exact match via
            # {"equals": ...}, sem tokenização/stemming (evita falso match).
            "categoria": {"type": "token"},
            "status": {"type": "token"},
        },
    }
}


def _apply_validator(db, coll_name, schema):
    """collMod com $jsonSchema — funciona em collection já existente (seed roda antes)."""
    try:
        db.command("collMod", coll_name, validator=schema, validationLevel="moderate", validationAction="warn")
        print(f"✓ $jsonSchema aplicado em '{coll_name}' (validationAction=warn — não bloqueia, só avisa)")
    except OperationFailure as e:
        print(f"⚠ não foi possível aplicar $jsonSchema em '{coll_name}': {str(e)[:120]}")


def _regular_indexes(db):
    db[config.CHAMADOS_COLL].create_index([("status", ASCENDING), ("created_at", DESCENDING)], name="status_created")
    db[config.CHAMADOS_COLL].create_index([("numero_chamado", ASCENDING)], name="numero_chamado", unique=True)
    db[config.PEDIDOS_COLL].create_index([("numero_pedido", ASCENDING)], name="numero_pedido", unique=True)
    db[config.CATALOGO_COLL].create_index([("categoria", ASCENDING)], name="categoria", unique=True)
    db[config.CATALOGO_FOTOS_COLL].create_index([("sku", ASCENDING), ("foto_idx", ASCENDING)], name="sku_foto", unique=True)
    print("✓ índices regulares criados (status_created, numero_chamado, numero_pedido, categoria, sku_foto)")


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
    _search_index(db[config.CATALOGO_FOTOS_COLL], config.CATALOGO_FOTOS_VECTOR_INDEX, CATALOGO_FOTOS_VECTOR_DEF, "vectorSearch")
    _apply_validator(db, config.CHAMADOS_COLL, CHAMADOS_SCHEMA)
    _apply_validator(db, config.PEDIDOS_COLL, PEDIDOS_SCHEMA)


if __name__ == "__main__":
    main()
