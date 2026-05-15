"""MinIO / S3 wrapper for raw document storage."""
from functools import lru_cache
from io import BytesIO

from minio import Minio

from app.core.config import settings


@lru_cache
def get_client() -> Minio:
    endpoint = settings.S3_ENDPOINT.replace("http://", "").replace("https://", "")
    secure = settings.S3_ENDPOINT.startswith("https://")
    return Minio(
        endpoint,
        access_key=settings.S3_ACCESS_KEY,
        secret_key=settings.S3_SECRET_KEY,
        secure=secure,
        region=settings.S3_REGION,
    )


def ensure_bucket() -> None:
    c = get_client()
    if not c.bucket_exists(settings.S3_BUCKET):
        c.make_bucket(settings.S3_BUCKET)


def put_object(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    ensure_bucket()
    c = get_client()
    c.put_object(settings.S3_BUCKET, key, BytesIO(data), length=len(data), content_type=content_type)


def get_object(key: str) -> bytes:
    c = get_client()
    resp = c.get_object(settings.S3_BUCKET, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()
