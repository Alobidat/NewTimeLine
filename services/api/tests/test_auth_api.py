"""Auth/account router + write-gate tests (ADR-0026).

No live DB: a small fake AsyncSession returns canned ``get``/``scalars`` results, so these
assert the wiring + the gate logic — that ``require_verified_actor`` blocks anonymous/
unverified/no-agreement callers, the providers endpoint reflects config, and the GDPR export
has the documented shape.

The async helpers are driven with ``asyncio.run`` (this package has no pytest-asyncio
config), so the tests pass under any pytest asyncio mode.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import chronos_core.accounts_repo as accounts_repo
from chronos_core.auth import session as auth_session
from chronos_core.models.config import Config
from chronos_core.models.user import User, UserAgreement
from chronos_api.auth_stub import require_verified_actor
from chronos_api.deps import get_session
from chronos_api.routers import account, auth


class FakeSession:
    """Routes ``get``/``scalars``/``execute`` to canned data keyed by model class."""

    def __init__(self, *, configs=None, agreements=None, user=None, scalars_queue=None):
        self._configs = configs or {}
        self._agreements = agreements or set()  # set of (user_id, version)
        self._user = user
        self._scalars_queue = list(scalars_queue or [])

    async def get(self, model, key):
        if model is Config:
            val = self._configs.get(key)
            return Config(key=key, value=val, scope="auth", version=1) if val is not None else None
        if model is UserAgreement:
            return UserAgreement(user_id=key[0], version=key[1]) if key in self._agreements else None
        if model is User:
            return self._user
        return None

    async def scalars(self, _stmt):
        return _Result(self._scalars_queue.pop(0) if self._scalars_queue else [])

    async def execute(self, _stmt):
        return _Result(self._scalars_queue.pop(0) if self._scalars_queue else [])

    async def flush(self):
        return None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


# --- require_verified_actor (the write gate) ------------------------------------------


def test_gate_blocks_anonymous():
    """No bearer token → 401."""
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_verified_actor(authorization=None, session=FakeSession()))
    assert exc.value.status_code == 401


def test_gate_blocks_unverified_email():
    uid = uuid.uuid4()
    token = auth_session.issue(uid, email_verified=False, agreement_version="v1")
    fake = FakeSession(configs={"auth.require_email_verified": True, "auth.agreement_version": "v1"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_verified_actor(authorization=f"Bearer {token}", session=fake))
    assert exc.value.status_code == 403


def test_gate_blocks_when_agreement_not_accepted():
    uid = uuid.uuid4()
    token = auth_session.issue(uid, email_verified=True, agreement_version="v1")
    fake = FakeSession(
        configs={"auth.require_email_verified": True, "auth.agreement_version": "v1"},
        agreements=set(),  # not accepted
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_verified_actor(authorization=f"Bearer {token}", session=fake))
    assert exc.value.status_code == 403


def test_gate_passes_verified_and_accepted():
    uid = uuid.uuid4()
    token = auth_session.issue(uid, email_verified=True, agreement_version="v1")
    fake = FakeSession(
        configs={"auth.require_email_verified": True, "auth.agreement_version": "v1"},
        agreements={(uid, "v1")},
    )
    actor = asyncio.run(require_verified_actor(authorization=f"Bearer {token}", session=fake))
    assert actor == uid


# --- /auth/providers reflects config --------------------------------------------------


def _app_with(session_factory):
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(account.router)

    async def _sess():
        yield session_factory()

    app.dependency_overrides[get_session] = _sess
    return app


def test_providers_empty_when_none_configured():
    fake = FakeSession(configs={"auth.providers": []})
    client = TestClient(_app_with(lambda: fake))
    resp = client.get("/auth/providers")
    assert resp.status_code == 200
    # No OAuth provider configured; the self-contained dev login is still offered (default on).
    assert resp.json() == {"providers": [], "dev_login": True}


def test_providers_dev_login_disabled():
    fake = FakeSession(configs={"auth.providers": [], "auth.dev_login_enabled": False})
    client = TestClient(_app_with(lambda: fake))
    resp = client.get("/auth/providers")
    assert resp.status_code == 200
    assert resp.json() == {"providers": [], "dev_login": False}


# --- dev email-code login -------------------------------------------------------------


def test_dev_login_start_returns_dev_code():
    """In non-prod /auth/dev/start echoes the emailed code so the flow is exercisable."""
    fake = FakeSession()
    client = TestClient(_app_with(lambda: fake))
    resp = client.post("/auth/dev/start", json={"email": "a@x.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is True
    assert body["dev_code"]  # a real, checkable code


def test_dev_login_disabled_404s():
    fake = FakeSession(configs={"auth.dev_login_enabled": False})
    client = TestClient(_app_with(lambda: fake))
    assert client.post("/auth/dev/start", json={"email": "a@x.com"}).status_code == 404
    assert (
        client.post("/auth/dev/verify", json={"email": "a@x.com", "code": "x"}).status_code
        == 404
    )


def test_dev_login_verify_issues_session(monkeypatch):
    """A valid code → a provisioned, email-verified user → a session JWT."""
    from chronos_core.auth import email as email_mod

    uid = uuid.uuid4()
    user = User(
        handle="a-abc", display_name=None, email="a@x.com",
        email_verified=True, reputation=0, prefs={},
    )
    user.id = uid
    user.created_at = datetime.now(timezone.utc)  # SessionToken.user (UserMe) needs it

    async def _fake_provision(session, **kw):
        assert kw["provider"] == "email"
        assert kw["provider_sub"] == "a@x.com"
        assert kw["email_verified"] is True
        return user, True

    monkeypatch.setattr(accounts_repo, "provision_from_identity", _fake_provision)

    fake = FakeSession()  # no agreement_version configured → needs_agreement False
    client = TestClient(_app_with(lambda: fake))
    code = email_mod.make_code("a@x.com")
    resp = client.post("/auth/dev/verify", json={"email": "a@x.com", "code": code})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["user_id"] == str(uid)
    assert body["email_verified"] is True
    # The issued JWT really resolves to this user.
    assert auth_session.verify(body["access_token"]).user_id == uid


def test_dev_login_verify_rejects_bad_code():
    fake = FakeSession()
    client = TestClient(_app_with(lambda: fake))
    resp = client.post("/auth/dev/verify", json={"email": "a@x.com", "code": "not-a-code"})
    assert resp.status_code == 400


# --- GDPR export shape ----------------------------------------------------------------


def test_export_user_shape():
    uid = uuid.uuid4()
    user = User(
        handle="alice-abc", display_name="Alice", email="a@x.com",
        email_verified=True, reputation=3, prefs={},
    )
    user.id = uid
    user.created_at = datetime.now(timezone.utc)
    # scalars() is called in fixed order: identities, agreements, comments, reactions,
    # votes, links, media_links — all empty here (we assert the envelope + user block).
    fake = FakeSession(user=user, scalars_queue=[[], [], [], [], [], [], []])
    archive = asyncio.run(accounts_repo.export_user(fake, uid))
    assert archive["schema"] == "chronos.user_export.v1"
    assert archive["user"]["handle"] == "alice-abc"
    assert archive["user"]["email"] == "a@x.com"
    for key in ("identities", "agreements", "comments", "reactions", "source_votes",
                "event_links", "media_links"):
        assert archive[key] == []
