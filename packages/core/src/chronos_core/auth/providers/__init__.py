"""Provider-agnostic OAuth2/OIDC auth providers (ADR-0026).

Mirrors the LLM provider registry (ADR-0014): a thin :class:`~chronos_core.auth.providers.base.AuthProvider`
interface, per-provider adapters in :mod:`oidc_providers`, and a config-driven
:mod:`registry`. The enabled set + client id/secret/scopes live in config/Settings, so adding
a provider is config, not code.
"""

from chronos_core.auth.providers.base import (
    AuthProvider,
    PkceChallenge,
    ProviderClaims,
    ProviderConfig,
    make_pkce,
)
from chronos_core.auth.providers.registry import get_provider, list_enabled_ids

__all__ = [
    "AuthProvider",
    "ProviderClaims",
    "ProviderConfig",
    "PkceChallenge",
    "make_pkce",
    "get_provider",
    "list_enabled_ids",
]
