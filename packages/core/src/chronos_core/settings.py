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
    # Browser/mobile-reachable S3 host used only to sign *direct upload* (presigned-PUT) URLs.
    # Empty → fall back to s3_endpoint (dev / single-host, where the client can reach MinIO too).
    # In prod this is the public TLS route to the object store (the internal s3_endpoint is not
    # reachable from clients); enabling direct upload also needs bucket CORS allowing PUT.
    s3_public_endpoint: str = Field(default="")
    s3_access_key: str = Field(default="chronos")
    s3_secret_key: str = Field(default="chronos")
    s3_bucket: str = Field(default="chronos-sources")

    # App.
    environment: str = Field(default="dev")
    log_level: str = Field(default="INFO")

    # Admin API gate (scaffold until OIDC/RBAC lands in Phase 4). When set, the Admin API
    # requires this bearer token; when empty in dev, admin access is open for convenience.
    admin_token: str = Field(default="")

    # Identity stub for interaction writes (ADR-0025). Until a JWT session is presented,
    # READS still resolve to this fixed dev/anonymous actor UUID for local convenience.
    # NOTE: this anonymous actor never satisfies ``require_verified_actor`` (write gate) —
    # only a verified, agreement-accepted JWT session does. Stable default → reproducible.
    dev_actor_id: str = Field(default="00000000-0000-0000-0000-000000000001")

    # --- Phase-4 accounts / auth (ADR-0026) --------------------------------------------
    # Session JWT (HS256, stdlib HMAC — no extra dependency). Set a strong secret per env;
    # the dev default lets the app boot but MUST be overridden in prod.
    jwt_secret: str = Field(default="dev-insecure-change-me")
    jwt_ttl_seconds: int = Field(default=60 * 60 * 24 * 14)  # 14 days
    jwt_issuer: str = Field(default="chronos")

    # OAuth2/OIDC provider client secrets, keyed by provider id. Non-secret toggles (enabled
    # set, scopes, redirect) live in the Config Service (auth.providers). A provider is only
    # offered when it is enabled in config AND has both a client_id (config) and secret (here).
    auth_google_client_secret: str = Field(default="")
    auth_apple_client_secret: str = Field(default="")
    auth_facebook_client_secret: str = Field(default="")
    auth_twitter_client_secret: str = Field(default="")

    # SMTP for email-verification mail. When host is empty the sender is a no-op console stub
    # (dev/tests) — the verification code is still issued + returned by the request endpoint
    # in non-prod so the flow is exercisable without a live SMTP.
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="no-reply@newtimeline.app")
    smtp_starttls: bool = Field(default=True)

    def provider_secret(self, provider: str) -> str:
        """Return the configured client secret for a provider id (empty if unset)."""
        return {
            "google": self.auth_google_client_secret,
            "apple": self.auth_apple_client_secret,
            "facebook": self.auth_facebook_client_secret,
            "twitter": self.auth_twitter_client_secret,
        }.get(provider, "")

    @property
    def sync_database_url(self) -> str:
        """Sync URL (psycopg) for Alembic migrations."""
        return self.database_url.replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    """Cached singleton settings."""
    return Settings()
