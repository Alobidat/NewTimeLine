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


@lru_cache
def _signing_client():
    """A boto3 client pointed at the *public* S3 host, used only to mint presigned URLs we hand
    to browsers/phones. Falls back to the internal endpoint when no public endpoint is set (dev /
    single-host). Separate from ``_client`` so internal reads/writes stay on the internal host."""
    import boto3
    from botocore.config import Config

    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_public_endpoint or s.s3_endpoint,
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


def presigned_put(key: str, *, content_type: str | None = None, expires: int = 3600) -> str:
    """A time-limited PUT URL the client uses to upload a clip **straight to the object store**,
    bypassing the API (so a big recording never streams through API memory). Signed against the
    public endpoint; the client must PUT with the same ``Content-Type`` it was signed for."""
    ensure_bucket()
    params = {"Bucket": get_settings().s3_bucket, "Key": key}
    if content_type:
        params["ContentType"] = content_type
    return _signing_client().generate_presigned_url(
        "put_object", Params=params, ExpiresIn=expires
    )


def head(key: str) -> dict | None:
    """Return ``{"size", "content_type"}`` for an object, or ``None`` if it doesn't exist —
    used to confirm a direct-uploaded clip actually landed before publishing its event."""
    from botocore.exceptions import ClientError

    try:
        obj = _client().head_object(Bucket=get_settings().s3_bucket, Key=key)
    except ClientError:
        return None
    return {"size": int(obj.get("ContentLength") or 0), "content_type": obj.get("ContentType")}
