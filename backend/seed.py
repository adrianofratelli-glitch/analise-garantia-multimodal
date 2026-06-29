"""Popula POC.chamados com os 15 chamados de garantia já resolvidos.

Para cada item de CHAMADOS_SEED:
  1. compor_frase(...)                  -> frase de análise (idêntica ao runtime)
  2. sobe seed_images/{arquivo} pro S3  -> URI s3:// (guardada no doc)
  3. embed_multimodal(input_type="document") -> vetor 1024-d (texto + imagem)
  4. insere em POC.chamados com tipo_defeito, status="resolvido", embedding

Idempotente: usa replace_one(upsert=True) por numero_chamado.

NÃO cria o índice de vetor — apenas IMPRIME o JSON do índice 'chamados_vector'
para você criar no Atlas (UI ou API). Rode depois do seed.

    python seed.py

Requer rede para Atlas, Voyage e S3 (rode no Codespaces, não no sandbox).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image
from pymongo import MongoClient

import s3
import voyage
from db import COLLECTION, DB_NAME, VECTOR_INDEX
from defeitos_catalog import (
    categoria_do_sku,
    compor_frase,
    derivar_tipo_defeito,
    nome_do_produto,
)
from seed_data import CHAMADOS_SEED

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SEED_IMAGES = Path(__file__).resolve().parents[1] / "seed_images"

# extensões aceitas para as fotos dos chamados (jpg/jpeg/png/webp)
IMG_EXTS = [".jpg", ".jpeg", ".png", ".webp"]

NOW = datetime.now(timezone.utc)


def resolver_imagem(arquivo: str) -> Path | None:
    """Acha a foto por nome-base, aceitando qualquer extensão de IMG_EXTS.

    Ex.: arquivo='cad_01.png' encontra cad_01.jpg, cad_01.jpeg ou cad_01.png.
    """
    stem = Path(arquivo).stem
    candidatos = [SEED_IMAGES / arquivo] + [SEED_IMAGES / f"{stem}{ext}" for ext in IMG_EXTS]
    for c in candidatos:
        if c.exists():
            return c
    return None

# Definição do índice de vetor a criar no Atlas (NÃO é criado por este script).
INDICE_VETOR = {
    "name": VECTOR_INDEX,
    "type": "vectorSearch",
    "definition": {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": voyage.EMBED_DIMS,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "categoria"},
            {"type": "filter", "path": "status"},
        ]
    },
}


CATEGORIAS_VALIDAS = {"cadeira", "colchao", "guarda_roupa"}


def main():
    parser = argparse.ArgumentParser(description="Popula POC.chamados com os chamados de garantia resolvidos.")
    parser.add_argument(
        "categorias",
        nargs="*",
        help="categorias a seedar (cadeira colchao guarda_roupa). Vazio = todas.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="apaga a collection antes de seedar (base limpa só com o que for seedado).",
    )
    args = parser.parse_args()

    selecionadas = set(args.categorias)
    invalidas = selecionadas - CATEGORIAS_VALIDAS
    if invalidas:
        sys.exit(f"Categoria(s) inválida(s): {', '.join(sorted(invalidas))}. Use: cadeira colchao guarda_roupa")

    itens = [
        i for i in CHAMADOS_SEED if not selecionadas or categoria_do_sku(i["sku"]) in selecionadas
    ]
    if not itens:
        sys.exit("Nenhum chamado para as categorias informadas.")
    if selecionadas:
        print(f"Seedando apenas: {', '.join(sorted(selecionadas))} ({len(itens)} chamados)\n")

    uri = os.getenv("MONGODB_URI")
    if not uri:
        sys.exit("MONGODB_URI não definida — copie .env.example para .env e preencha.")

    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    client.admin.command("ping")
    coll = client[DB_NAME][COLLECTION]

    if args.reset:
        removidos = coll.delete_many({}).deleted_count
        print(f"  reset: {removidos} documentos removidos\n")

    inseridos = 0
    for item in itens:
        sku = item["sku"]
        categoria = categoria_do_sku(sku)
        checklist = item["checklist"]

        # 1. frase IDÊNTICA à do runtime (mesma função de defeitos_catalog)
        frase = compor_frase(sku, checklist, item["descricao"])

        # 2. abre a imagem local (jpg/jpeg/png) e sobe pro S3
        caminho = resolver_imagem(item["arquivo"])
        if caminho is None:
            stem = Path(item["arquivo"]).stem
            sys.exit(
                f"Imagem não encontrada: {SEED_IMAGES}/{stem}.(jpg|jpeg|png)\n"
                "Adicione a foto em seed_images/ ou gere placeholders com: "
                "python seed_images/gen_placeholders.py"
            )
        imagem = Image.open(caminho).convert("RGB")
        with open(caminho, "rb") as fh:
            up = s3.upload_bytes(fh.read(), caminho.name, prefixo="seed")

        # 3. embedding multimodal (texto + imagem), input_type="document"
        embedding = voyage.embed_multimodal(frase, imagem, input_type="document")

        # 4. grava o chamado resolvido
        doc = {
            "numero_chamado": item["numero_chamado"],
            "sku": sku,
            "nome_produto": nome_do_produto(sku),
            "categoria": categoria,
            "checklist": checklist,
            "descricao": item["descricao"],
            "frase_analise": frase,
            "tipo_defeito": derivar_tipo_defeito(sku, checklist),
            "imagem_uri": up["uri"],
            "arquivo": caminho.name,
            "status": "resolvido",
            "resolucao_final": item["resolucao_final"],
            "veredito": item["veredito"],
            "origem": "seed",
            "created_at": NOW,
            "embedding": embedding,
        }
        coll.replace_one({"numero_chamado": item["numero_chamado"]}, doc, upsert=True)
        inseridos += 1
        print(f"  ✓ {item['numero_chamado']:<12} {sku:<12} dims={len(embedding)}")

    total = coll.count_documents({})
    resolvidos = coll.count_documents({"status": "resolvido"})
    print(f"\nSeed concluído em {DB_NAME}.{COLLECTION}:")
    print(f"  processados neste run : {inseridos}")
    print(f"  total na collection   : {total}")
    print(f"  status=resolvido      : {resolvidos}")

    por_categoria = coll.aggregate(
        [{"$group": {"_id": "$categoria", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
    )
    print("  por categoria         :")
    for row in por_categoria:
        print(f"    - {row['_id']:<14} {row['n']}")

    print("\n" + "=" * 72)
    print(f"Crie ESTE índice de vetor no Atlas ({DB_NAME}.{COLLECTION}):")
    print("=" * 72)
    print(json.dumps(INDICE_VETOR, indent=2, ensure_ascii=False))
    print("=" * 72)
    print("Sem este índice, o $vectorSearch do /analisar não funciona.")


if __name__ == "__main__":
    main()
