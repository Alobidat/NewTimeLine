"""Provider-agnostic OAuth2/OIDC auth — the abstraction the registry builds from (ADR-0026).

Mirrors the LLM provider pattern (ADR-0014): a thin interface + per-provider adapters, with
the *enabled set + client id/secret/scopes in config*, so adding a provider is config, not
code. Each adapter declares its ``authorize_url`` / ``token_url`` / ``userinfo_url`` and one
**pure** function, :meth:`AuthProvider.extract_claims`, mapping a provider's token+userinfo
response to a normalised :class:`ProviderClaims`. That purity is what makes claim-extraction
unit-testable (respx mocks the HTTP, the mapping is plain data-in/data-out).

Flow per provider (authorization-code + PKCE):
1. :func:`build_authorize` → (authorize URL, PKCE verifier, state) for the client to redirect.
2. callback exchanges ``code`` (+verifier) at ``token_url`` → tokens.
3. (OIDC) decode the id_token claims and/or call ``userinfo_url`` → raw claims.
4. :meth:`extract_claims` → normalised (provider_sub, email, email_verified, name).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderClaims:
    """The normalised identity facts we need from any provider."""

    provider: str
    provider_sub: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    avatar: str | None = None  # profile picture URL (the OIDC ``picture`` claim), when present


@dataclass(frozen=True)
class ProviderConfig:
    """The resolved config for one enabled provider (config toggle + env secret)."""

    id: str
    client_id: str
    client_secret: str
    scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PkceChallenge:
    """A PKCE pair: the secret ``verifier`` (kept by the client) + derived ``challenge``."""

    verifier: str
    challenge: str
    method: str = "S256"


def make_pkce() -> PkceChallenge:
    """Generate an S256 PKCE verifier/challenge pair (RFC 7636)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return PkceChallenge(verifier=verifier, challenge=challenge)


class AuthProvider:
    """Base OAuth2/OIDC adapter. Subclasses set the URLs + ``extract_claims``.

    The HTTP calls (token exchange, userinfo) live in :mod:`chronos_core.auth.oauth` so this
    class stays a pure declaration of endpoints + the claim mapping — the testable core.
    """

    id: str = ""
    authorize_url: str = ""
    token_url: str = ""
    userinfo_url: str | None = None
    # Whether the OIDC id_token already carries the identity claims (skip userinfo call).
    uses_id_token: bool = False

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def authorize_params(self, *, redirect_uri: str, challenge: PkceChallenge, state: str) -> dict[str, str]:
        """The query params for the authorization redirect. Overridable per provider."""
        return {
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "state": state,
            "code_challenge": challenge.challenge,
            "code_challenge_method": challenge.method,
        }

    def token_params(self, *, code: str, redirect_uri: str, verifier: str) -> dict[str, str]:
        """Form body for the authorization-code → token exchange. Overridable per provider."""
        return {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code_verifier": verifier,
        }

    def extract_claims(self, token_response: dict, userinfo: dict | None) -> ProviderClaims:
        """Map a provider's raw token + userinfo response to normalised claims. PURE — no I/O.

        Must be implemented per provider; this is the unit-tested seam.
        """
        raise NotImplementedError
