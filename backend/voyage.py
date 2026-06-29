"""Cliente Voyage AI — embedding multimodal MANUAL (Caminho B).

Usamos voyage-multimodal-3 via SDK `voyageai` para gerar UM vetor de 1024
dimensões a partir de texto + imagem juntos. Esse vetor é o que vai pro
$vectorSearch do Atlas.

IMPORTANTE: não usamos autoEmbed do Atlas — autoEmbed é text-only e não enxerga
a imagem. Aqui o embedding é multimodal e calculado pela aplicação, tanto no
seed (input_type="document") quanto no runtime (input_type="query").
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL = "voyage-multimodal-3"
EMBED_DIMS = 1024

_client = None


def get_client():
    """Cliente voyageai preguiçoso (lê VOYAGE_API_KEY do ambiente)."""
    global _client
    if _client is None:
        import voyageai

        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY não definida. Copie .env.example para .env e preencha a chave da Voyage."
            )
        _client = voyageai.Client(api_key=api_key)
    return _client


def embed_multimodal(frase: str, imagem_pil, input_type: str) -> list[float]:
    """Gera o embedding multimodal (texto + imagem) de UM chamado.

    Args:
        frase: texto da análise (saída de compor_frase()).
        imagem_pil: PIL.Image.Image da foto do produto.
        input_type: "document" no seed, "query" no runtime.

    Returns:
        Lista de 1024 floats (vetor cosine-normalizado pela Voyage).
    """
    if input_type not in ("document", "query"):
        raise ValueError("input_type deve ser 'document' (seed) ou 'query' (runtime).")

    client = get_client()
    # Cada "input" é uma sequência intercalando texto e imagem(ns) PIL.
    result = client.multimodal_embed(
        inputs=[[frase, imagem_pil]],
        model=MODEL,
        input_type=input_type,
    )
    return result.embeddings[0]
