"""Identity resolution + the write gate (ADR-0025 → ADR-0026).

This module is the single seam every interaction write goes through. Two dependencies:

- :func:`get_actor` — resolve the caller to a user id. Reads a ``Bearer`` **session JWT**
  (issued at login) and returns the user id it carries. With **no token** it falls back to the
  fixed dev/anonymous actor (``settings.dev_actor_id``) so anonymous **reads** keep working and
  the local dev box needs no auth. The router seam is unchanged from the ADR-0025 stub: every
  endpoint that did ``Depends(get_actor)`` still works.

- :func:`require_verified_actor` — the **write gate**. It 401/403s unless the caller is signed
  in (valid JWT, not the anonymous fallback), email-verified, AND has accepted the *current*
  agreement version. Interaction/link write endpoints depend on THIS; reads stay open.

The anonymous fallback can never satisfy :func:`require_verified_actor` (it returns
``None`` from :func:`_session_claims`), so an unauthenticated caller is always blocked from
writes even when no providers are configured.
"""

from __future__ import annotations

import uuid

from chronos_core import accounts_repo, config_service
from chronos_core.auth import session as auth_session
from chronos_core.settings import get_settings
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    token = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
    return token or None


def _session_claims(authorization: str | None) -> auth_session.SessionClaims | None:
    """Decode the bearer session JWT to claims, or ``None`` if absent/invalid."""
    token = _bearer(authorization)
    if token is None:
        return None
    try:
        return auth_session.verify(token)
    except Exception:  # noqa: BLE001 - any decode/verify failure → treat as anonymous
        return None


def get_actor(authorization: str | None = Header(default=None)) -> uuid.UUID:
    """Resolve the current user id for a request.

    A valid session JWT → its user id. No/invalid token → the dev/anonymous actor (reads only;
    this id never passes :func:`require_verified_actor`).
    """
    claims = _session_claims(authorization)
    if claims is not None:
        return claims.user_id
    settings = get_settings()
    try:
        return uuid.UUID(settings.dev_actor_id)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "dev_actor_id is not a valid UUID"
        ) from exc


async def require_verified_actor(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> uuid.UUID:
    """Write gate: require a signed-in, email-verified, current-agreement-accepted caller.

    - No/invalid session token → **401** (anonymous can read but not write).
    - Email not verified (when verification is required) → **403**.
    - Current agreement not accepted → **403**.
    Returns the caller's user id on success.
    """
    claims = _session_claims(authorization)
    if claims is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required to interact")

    require_verified = bool(
        await config_service.get(session, "auth.require_email_verified", True)
    )
    if require_verified and not claims.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "verify your email to interact")

    version = await config_service.get(session, "auth.agreement_version", "")
    if version and not await accounts_repo.has_accepted(session, claims.user_id, version):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "accept the current agreement to interact"
        )
    return claims.user_id
