"""Minimal HS256 JWT (encode/decode) on the standard library — no extra dependency.

Phase-4 sessions are signed JWTs (ADR-0026). We sign with HMAC-SHA256 using ``jwt_secret``
from Settings. Keeping this a tiny, pure, well-tested function (rather than pulling in PyJWT)
matches the token-economy / minimal-deps standard and keeps the verify path trivially
unit-testable. Only the algorithm we issue (HS256) is accepted on decode (no ``alg=none``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

ALG = "HS256"


class JWTError(Exception):
    """Raised when a token is malformed, mis-signed, or expired."""


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(seg: str) -> bytes:
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)


def encode(payload: dict[str, Any], secret: str) -> str:
    """Sign ``payload`` as a compact HS256 JWT. ``payload`` should already carry claims
    (``sub``/``exp``/``iss``/…); this only adds the header + signature."""
    header = {"alg": ALG, "typ": "JWT"}
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    segments.append(_b64url(sig))
    return ".".join(segments)


def decode(token: str, secret: str, *, verify_exp: bool = True) -> dict[str, Any]:
    """Verify signature (constant-time) + expiry and return the claims. Raises ``JWTError``."""
    try:
        header_seg, payload_seg, sig_seg = token.split(".")
    except ValueError as exc:
        raise JWTError("malformed token") from exc

    try:
        header = json.loads(_b64url_decode(header_seg))
    except Exception as exc:  # noqa: BLE001 - any decode failure is a bad token
        raise JWTError("bad header") from exc
    if header.get("alg") != ALG:
        raise JWTError("unexpected alg")

    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        given = _b64url_decode(sig_seg)
    except Exception as exc:  # noqa: BLE001
        raise JWTError("bad signature encoding") from exc
    if not hmac.compare_digest(expected, given):
        raise JWTError("signature mismatch")

    try:
        claims = json.loads(_b64url_decode(payload_seg))
    except Exception as exc:  # noqa: BLE001
        raise JWTError("bad payload") from exc

    if verify_exp and "exp" in claims and int(time.time()) >= int(claims["exp"]):
        raise JWTError("token expired")
    return claims
