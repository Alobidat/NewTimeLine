"""Session tokens — issue/validate the signed-JWT the API hands clients after login.

A session encodes the user id (``sub``), email-verified flag, and the agreement version the
user had accepted at issue time, so the cheap read path (``get_actor``) needs no DB hit. The
authoritative gate (``require_verified_actor``) still re-checks the DB on writes, so a token
can't outlive a revoked/anonymised account. Pure functions over :mod:`chronos_core.auth.jwt`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from chronos_core.auth import jwt
from chronos_core.settings import get_settings


@dataclass(frozen=True)
class SessionClaims:
    """Decoded session: who the caller is + what their token asserts."""

    user_id: uuid.UUID
    email_verified: bool
    agreement_version: str | None


def issue(
    user_id: uuid.UUID,
    *,
    email_verified: bool,
    agreement_version: str | None,
    ttl_seconds: int | None = None,
) -> str:
    """Mint a session JWT for a user. TTL + secret + issuer come from Settings."""
    settings = get_settings()
    now = int(time.time())
    ttl = ttl_seconds if ttl_seconds is not None else settings.jwt_ttl_seconds
    payload = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + ttl,
        "ev": bool(email_verified),
        "av": agreement_version,
    }
    return jwt.encode(payload, settings.jwt_secret)


def verify(token: str) -> SessionClaims:
    """Decode + validate a session JWT into :class:`SessionClaims`. Raises ``jwt.JWTError``."""
    claims = jwt.decode(token, get_settings().jwt_secret)
    return SessionClaims(
        user_id=uuid.UUID(claims["sub"]),
        email_verified=bool(claims.get("ev", False)),
        agreement_version=claims.get("av"),
    )
