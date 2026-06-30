"""Armazenamento de imagens — backend LOCAL (PoV).

Padrão correto de blob storage: os BYTES da imagem NUNCA vão para o MongoDB
(isso incharia o cluster, backups e working set). O Mongo guarda só a referência
(uri) + metadados + o vetor; o blob vive fora.

No PoV o blob fica em disco local (MEDIA_ROOT) e é servido pelo FastAPI em
MEDIA_URL_PREFIX. Em produção, basta reimplementar upload_imagem/url_for com
boto3 (S3) — a interface (uri, url) é idêntica à do antigo s3.py, então
seed.py e main.py não mudam.
"""

from pathlib import Path

import config

URI_SCHEME = "file://"


def upload_imagem(imagem_bytes: bytes, key: str, content_type: str) -> tuple[str, str]:
    """Grava os bytes em MEDIA_ROOT/<key>.

    Retorna (uri, url): a uri (file://<key>) persiste no documento; a url
    (/media/<key>) é o que o frontend usa no <img src>.
    `content_type` é aceito por compatibilidade de interface (não usado em disco).
    """
    dest = config.MEDIA_ROOT / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(imagem_bytes)
    return f"{URI_SCHEME}{key}", url_for(f"{URI_SCHEME}{key}")


def url_for(uri: str) -> str:
    """Converte uma uri file://<key> na URL pública servida pelo FastAPI."""
    key = uri.removeprefix(URI_SCHEME).lstrip("/")
    return f"{config.MEDIA_URL_PREFIX}/{key}"


def path_for(key: str) -> Path:
    return config.MEDIA_ROOT / key.removeprefix(URI_SCHEME).lstrip("/")
