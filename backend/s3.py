"""Upload das imagens dos chamados para o S3 (boto3).

O MongoDB NÃO guarda a imagem — guarda só a URI s3:// + metadados + o vetor.
Aqui subimos os bytes da foto e devolvemos a URI s3:// (persistida no chamado)
e uma presigned URL (para o frontend exibir a foto temporariamente).

Env: S3_BUCKET, AWS_REGION (+ credenciais AWS padrão do boto3).
"""

import os
import uuid
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PRESIGN_EXPIRES = 3600  # 1h

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION"))
    return _s3


def _bucket() -> str:
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        raise RuntimeError(
            "S3_BUCKET não definida. Copie .env.example para .env e preencha o bucket."
        )
    return bucket


def _content_type(arquivo: str) -> str:
    ext = arquivo.lower().rsplit(".", 1)[-1]
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "application/octet-stream")


def upload_bytes(data: bytes, arquivo: str, prefixo: str = "chamados") -> dict:
    """Sobe `data` para s3://<bucket>/<prefixo>/<arquivo> e devolve as URIs.

    Returns:
        {"uri": "s3://...", "url": "https://...presigned...", "key": "..."}
    """
    bucket = _bucket()
    # nome único para não sobrescrever uploads de runtime
    nome = arquivo if prefixo == "seed" else f"{uuid.uuid4().hex}_{arquivo}"
    key = f"{prefixo}/{nome}"

    _client().put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=_content_type(arquivo),
    )
    return {
        "uri": f"s3://{bucket}/{key}",
        "url": presigned_url(key),
        "key": key,
    }


def presigned_url(key: str) -> str:
    """Gera uma presigned URL de leitura para exibir a imagem no frontend."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=PRESIGN_EXPIRES,
    )


def presigned_url_from_uri(uri: str) -> str:
    """Recebe uma URI s3://bucket/key e devolve uma presigned URL de leitura."""
    if not uri.startswith("s3://"):
        return uri
    _, _, rest = uri.partition("s3://")
    _, _, key = rest.partition("/")
    return presigned_url(key)


def enabled() -> bool:
    """True se o object storage estiver configurado (S3_BUCKET definido)."""
    return bool(os.getenv("S3_BUCKET"))


def try_upload(data: bytes, arquivo: str, prefixo: str = "chamados") -> str | None:
    """Best-effort: sobe pro S3 se configurado; devolve a URI s3:// ou None.

    Nunca levanta — se o storage não estiver configurado ou o upload falhar,
    retorna None e a aplicação segue (object storage é opcional na PoV).
    """
    if not enabled():
        return None
    try:
        return upload_bytes(data, arquivo, prefixo)["uri"]
    except Exception as e:  # noqa: BLE001
        print(f"[s3] upload best-effort falhou, seguindo sem persistir: {e}")
        return None
