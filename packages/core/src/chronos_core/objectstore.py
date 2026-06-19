"""Thin S3-compatible object-store client (MinIO locally, any S3 in prod).

Used by the media-archival workers to store/serve captured media binaries. boto3 is
imported lazily so importing this module (and thus chronos_core) stays cheap and doesn't
require boto3 unless the store is actually used. Connection comes from Settings (ADR-0004:
standard S3 API, no vendor SDK beyond boto3 which speaks to any S3).
"""

from __future__ import annotations

from functools import lru_cache

from chronos_core.settings import get_settings


@lru_cache
def _client():
    """Build (once) a boto3 S3 client pointed at the configured endpoint."""
    import boto3  # lazy: only when the store is actually used
    from botocore.config import Config

    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    """Create the configured bucket if it does not exist (idempotent)."""
    from botocore.exceptions import ClientError

    client = _client()
    bucket = get_settings().s3_bucket
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def put_bytes(key: str, data: bytes, *, content_type: str | None = None) -> str:
    """Store ``data`` under ``key`` and return the key. Ensures the bucket exists."""
    ensure_bucket()
    extra = {"ContentType": content_type} if content_type else {}
    _client().put_object(Bucket=get_settings().s3_bucket, Key=key, Body=data, **extra)
    return key


def get_bytes(key: str) -> bytes:
    """Read an object's bytes (used by the API to serve stored media)."""
    obj = _client().get_object(Bucket=get_settings().s3_bucket, Key=key)
    return obj["Body"].read()


def delete(key: str) -> None:
    """Delete an object (used when a stored item is released after proving durable)."""
    _client().delete_object(Bucket=get_settings().s3_bucket, Key=key)


def presigned_get(key: str, *, expires: int = 3600) -> str:
    """A time-limited GET URL for the API to hand clients (deferred serving path)."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": get_settings().s3_bucket, "Key": key},
        ExpiresIn=expires,
    )
