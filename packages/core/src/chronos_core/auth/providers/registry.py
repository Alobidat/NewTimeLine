"""Auth provider registry — builds enabled :class:`AuthProvider` adapters from config.

Mirrors the LLM provider registry (chronos_core.llm.factory, ADR-0014): the non-secret half
(enabled flag, client_id, scopes) comes from the Config Service key ``auth.providers``; the
client SECRET comes from Settings (env). A provider is **offered** only when it is enabled AND
has a client_id (config) AND a secret (env) — so a fresh box with nothing configured exposes
no providers and ``/auth/providers`` returns ``[]``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core import config_service
from chronos_core.auth.providers.base import AuthProvider, ProviderConfig
from chronos_core.auth.providers.oidc_providers import ADAPTERS
from chronos_core.settings import get_settings


async def _provider_configs(session: AsyncSession) -> list[dict]:
    return await config_service.get(session, "auth.providers", []) or []


async def list_enabled_ids(session: AsyncSession) -> list[str]:
    """The provider ids ready to offer clients (enabled + client_id + secret present)."""
    settings = get_settings()
    ids: list[str] = []
    for cfg in await _provider_configs(session):
        pid = cfg.get("id")
        if (
            pid in ADAPTERS
            and cfg.get("enabled")
            and cfg.get("client_id")
            and settings.provider_secret(pid)
        ):
            ids.append(pid)
    return ids


async def get_provider(session: AsyncSession, provider_id: str) -> AuthProvider | None:
    """Build the adapter for ``provider_id`` if it is enabled+configured, else ``None``."""
    settings = get_settings()
    for cfg in await _provider_configs(session):
        if cfg.get("id") != provider_id:
            continue
        adapter_cls = ADAPTERS.get(provider_id)
        secret = settings.provider_secret(provider_id)
        if not (adapter_cls and cfg.get("enabled") and cfg.get("client_id") and secret):
            return None
        return adapter_cls(
            ProviderConfig(
                id=provider_id,
                client_id=cfg["client_id"],
                client_secret=secret,
                scopes=list(cfg.get("scopes", [])),
            )
        )
    return None
