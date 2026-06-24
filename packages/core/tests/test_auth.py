"""Unit tests for the Phase-4 auth core (ADR-0026): JWT round-trip, PKCE, per-provider
pure claim-extraction (respx-mocked token/userinfo), and the migration import + export shape.

All pure / mocked — no live DB or network (matching the rest of the core test suite).
"""

from __future__ import annotations

import base64
import importlib
import json
import time
import uuid

import httpx
import pytest
import respx

from chronos_core.auth import jwt
from chronos_core.auth import session as auth_session
from chronos_core.auth.providers import make_pkce
from chronos_core.auth.providers import oauth
from chronos_core.auth.providers.base import ProviderConfig
from chronos_core.auth.providers.oidc_providers import (
    AppleProvider,
    FacebookProvider,
    GoogleProvider,
    TwitterProvider,
)


# --- JWT + session --------------------------------------------------------------------


def test_jwt_round_trip_and_tamper_detection():
    payload = {"sub": "abc", "exp": int(time.time()) + 60}
    token = jwt.encode(payload, "secret")
    assert jwt.decode(token, "secret")["sub"] == "abc"
    # Wrong secret → signature mismatch.
    with pytest.raises(jwt.JWTError):
        jwt.decode(token, "other-secret")
    # Tampered payload → signature mismatch.
    head, _, sig = token.split(".")
    forged = json.dumps({"sub": "evil"}).encode()
    bad = head + "." + base64.urlsafe_b64encode(forged).rstrip(b"=").decode() + "." + sig
    with pytest.raises(jwt.JWTError):
        jwt.decode(bad, "secret")


def test_jwt_rejects_expired():
    token = jwt.encode({"sub": "x", "exp": int(time.time()) - 1}, "secret")
    with pytest.raises(jwt.JWTError):
        jwt.decode(token, "secret")


def test_session_issue_verify_round_trip():
    uid = uuid.uuid4()
    token = auth_session.issue(uid, email_verified=True, agreement_version="2026-06-21")
    claims = auth_session.verify(token)
    assert claims.user_id == uid
    assert claims.email_verified is True
    assert claims.agreement_version == "2026-06-21"


def test_pkce_challenge_is_s256_and_unique():
    a, b = make_pkce(), make_pkce()
    assert a.method == "S256"
    assert a.verifier != b.verifier
    assert a.challenge != a.verifier  # challenge is the hash, not the verifier


# --- per-provider pure claim extraction (respx-mocked token/userinfo) ------------------


def _seg(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def _id_token(claims: dict) -> str:
    """A fake unsigned id_token: header.payload.sig with the given claims."""
    return f"{_seg({'alg': 'RS256'})}.{_seg(claims)}.sig"


def _cfg(pid: str) -> ProviderConfig:
    return ProviderConfig(id=pid, client_id="cid", client_secret="secret", scopes=["openid"])


@respx.mock
async def test_google_claims_from_id_token():
    idt = _id_token({"sub": "g-123", "email": "u@example.com", "email_verified": True, "name": "U"})
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"id_token": idt, "access_token": "at"})
    )
    p = GoogleProvider(_cfg("google"))
    claims = await oauth.resolve_claims(p, code="c", redirect_uri="https://x/cb", verifier="v")
    assert claims.provider == "google"
    assert claims.provider_sub == "g-123"
    assert claims.email == "u@example.com"
    assert claims.email_verified is True


@respx.mock
async def test_apple_claims_handle_string_email_verified():
    idt = _id_token({"sub": "a-9", "email": "relay@privaterelay.appleid.com", "email_verified": "true"})
    respx.post("https://appleid.apple.com/auth/token").mock(
        return_value=httpx.Response(200, json={"id_token": idt})
    )
    p = AppleProvider(_cfg("apple"))
    claims = await oauth.resolve_claims(p, code="c", redirect_uri="https://x/cb", verifier="v")
    assert claims.provider_sub == "a-9"
    assert claims.email_verified is True  # Apple sends the string "true"


@respx.mock
async def test_facebook_claims_marked_unverified():
    respx.post("https://graph.facebook.com/v18.0/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "at"})
    )
    respx.get(url__startswith="https://graph.facebook.com/me").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "fb-1", "name": "F", "email": "f@x.com",
                "picture": {"data": {"url": "https://fb/p.jpg"}},
            },
        )
    )
    p = FacebookProvider(_cfg("facebook"))
    claims = await oauth.resolve_claims(p, code="c", redirect_uri="https://x/cb", verifier="v")
    assert claims.provider_sub == "fb-1"
    assert claims.email == "f@x.com"
    assert claims.email_verified is False  # FB email always requires our own verification
    assert claims.avatar == "https://fb/p.jpg"


@respx.mock
async def test_twitter_claims_from_nested_data():
    respx.post("https://api.twitter.com/2/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "at"})
    )
    respx.get(url__startswith="https://api.twitter.com/2/users/me").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": "tw-7", "username": "handle",
                           "profile_image_url": "https://tw/p.jpg"}},
        )
    )
    p = TwitterProvider(_cfg("twitter"))
    claims = await oauth.resolve_claims(p, code="c", redirect_uri="https://x/cb", verifier="v")
    assert claims.provider_sub == "tw-7"
    assert claims.email is None
    assert claims.email_verified is False
    assert claims.avatar == "https://tw/p.jpg"


# --- migration import -----------------------------------------------------------------


def test_migration_0006_imports_and_is_chained():
    import pathlib

    # Resolve relative to this test file so it works regardless of pytest rootdir/CWD.
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    path = repo_root / "db" / "migrations" / "versions" / "0006_accounts.py"
    spec = importlib.util.spec_from_file_location("mig_0006", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0006"
    assert mod.down_revision == "0005"
    assert callable(mod.upgrade) and callable(mod.downgrade)
