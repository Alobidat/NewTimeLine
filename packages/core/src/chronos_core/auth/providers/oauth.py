"""OAuth HTTP I/O: build the authorize URL, exchange the code, fetch userinfo.

The only network code in the auth provider layer. Adapters (base.py / oidc_providers.py) stay
pure declarations; the callback router calls these three functions, then the adapter's pure
``extract_claims`` maps the responses → normalised :class:`ProviderClaims`. HTTP is mocked
with respx in tests.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from chronos_core.auth.providers.base import AuthProvider, PkceChallenge, ProviderClaims

_TIMEOUT = httpx.Timeout(15.0)


def build_authorize_url(
    provider: AuthProvider, *, redirect_uri: str, challenge: PkceChallenge, state: str
) -> str:
    """The full provider authorization URL the client should redirect the user to."""
    params = provider.authorize_params(redirect_uri=redirect_uri, challenge=challenge, state=state)
    return f"{provider.authorize_url}?{urlencode(params)}"


async def exchange_code(
    provider: AuthProvider, *, code: str, redirect_uri: str, verifier: str
) -> dict:
    """POST the authorization code to the provider's token endpoint → token response dict."""
    body = provider.token_params(code=code, redirect_uri=redirect_uri, verifier=verifier)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            provider.token_url,
            data=body,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_userinfo(provider: AuthProvider, access_token: str) -> dict | None:
    """GET the provider userinfo/API endpoint (when it has one) with the access token."""
    if not provider.userinfo_url:
        return None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            provider.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def resolve_claims(
    provider: AuthProvider, *, code: str, redirect_uri: str, verifier: str
) -> ProviderClaims:
    """Full callback path: exchange code → (maybe) fetch userinfo → pure extract_claims."""
    token_response = await exchange_code(
        provider, code=code, redirect_uri=redirect_uri, verifier=verifier
    )
    userinfo = None
    if not provider.uses_id_token:
        userinfo = await fetch_userinfo(provider, token_response.get("access_token", ""))
    return provider.extract_claims(token_response, userinfo)
