"""Process settings loaded from environment (12-factor). Shared by api + agents.

Cloud-agnostic: only standard connection URLs, no vendor SDKs (ADR-0004).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Connection + runtime settings. Override via env vars (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Data layer (standard URLs; async drivers).
    database_url: str = Field(
        default="postgresql+asyncpg://chronos:chronos@localhost:5432/chronos"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    amqp_url: str = Field(default="amqp://chronos:chronos@localhost:5672/")

    # Object store (S3-compatible; MinIO locally).
    s3_endpoint: str = Field(default="http://localhost:9000")
    s3_access_key: str = Field(default="chronos")
    s3_secret_key: str = Field(default="chronos")
    s3_bucket: str = Field(default="chronos-sources")

    # App.
    environment: str = Field(default="dev")
    log_level: str = Field(default="INFO")

    # Admin API gate (scaffold until OIDC/RBAC lands in Phase 4). When set, the Admin API
    # requires this bearer token; when empty in dev, admin access is open for convenience.
    admin_token: str = Field(default="")

    # Identity stub for interaction writes (ADR-0025). Until Phase-4 OIDC lands, every
    # interaction (comment/reaction/vote/link) is attributed to this fixed dev/anonymous
    # actor UUID. Phase 4 replaces the get_actor stub body with the real session lookup;
    # this key then becomes unused. Stable default so dev writes are reproducible.
    dev_actor_id: str = Field(default="00000000-0000-0000-0000-000000000001")

    @property
    def sync_database_url(self) -> str:
        """Sync URL (psycopg) for Alembic migrations."""
        return self.database_url.replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    """Cached singleton settings."""
    return Settings()
