"""Router request/response-shape tests for the interaction API (ADR-0025).

No DB: ``get_session`` is overridden with a no-op and the repository helpers are
monkeypatched, so these assert the wiring — actor injection via the ``get_actor`` stub, DTO
serialization, status codes, and the user-vs-agent link distinction — not persistence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import chronos_core.interactions_repo as repo
import chronos_core.notifications_repo as nrepo
import chronos_core.social_repo as srepo
import chronos_api.graph_queries as gq
import pytest
from chronos_api.auth_stub import get_actor, require_verified_actor
from chronos_api.deps import get_session
from chronos_api.routers import interactions, links
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _Comment:
    """Stand-in row with the attributes CommentRead reads off (from_attributes)."""

    def __init__(self, **kw):
        now = datetime.now(timezone.utc)
        self.id = kw.get("id", uuid.uuid4())
        self.event_id = kw["event_id"]
        self.user_id = kw["user_id"]
        self.parent_id = kw.get("parent_id")
        self.body = kw["body"]
        self.score = 0
        self.status = kw.get("status", "visible")
        self.created_at = now
        self.updated_at = now


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(interactions.router)
    app.include_router(links.router)

    class _EmptyResult:
        def all(self):
            return []

        def first(self):
            return None

    class _FakeSession:
        """Minimal stand-in: the mutating endpoints flush so the post-write aggregate
        reflects the change; the repo helpers are monkeypatched, so flush is all that's used.
        ``scalars``/``execute``/``get`` return empty so the comment-author/reaction enrichment
        degrades to no author + no reactions in these wiring tests."""

        async def flush(self):
            return None

        async def scalars(self, *_a, **_k):
            return _EmptyResult()

        async def execute(self, *_a, **_k):
            return _EmptyResult()

        async def get(self, *_a, **_k):
            return None

    async def _fake_session():
        yield _FakeSession()

    app.dependency_overrides[get_session] = _fake_session
    # Write endpoints now depend on the Phase-4 write gate (require_verified_actor); these
    # wiring tests stand in a fixed verified actor so they still assert the same plumbing.
    # The gate itself is unit-tested in test_auth.py (anonymous → 401).
    app.dependency_overrides[require_verified_actor] = get_actor
    return TestClient(app)


def test_create_comment_injects_actor_and_returns_201(client, monkeypatch):
    captured = {}

    async def fake_create_comment(session, *, event_id, user_id, body, parent_id=None):
        captured.update(event_id=event_id, user_id=user_id, body=body, parent_id=parent_id)
        return _Comment(event_id=event_id, user_id=user_id, body=body, parent_id=parent_id)

    monkeypatch.setattr(repo, "create_comment", fake_create_comment)

    ev = uuid.uuid4()
    resp = client.post(f"/events/{ev}/comments", json={"body": "hello"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["body"] == "hello"
    # The actor came from the get_actor stub, not the request body.
    assert captured["user_id"] == get_actor(None)
    assert str(captured["event_id"]) == str(ev)


def test_edit_comment_forbidden_when_not_author(client, monkeypatch):
    async def fake_edit(session, comment_id, *, user_id, body):
        raise PermissionError("not the comment author")

    monkeypatch.setattr(repo, "edit_comment", fake_edit)
    resp = client.patch(
        f"/events/{uuid.uuid4()}/comments/{uuid.uuid4()}", json={"body": "x"}
    )
    assert resp.status_code == 403


def test_toggle_reaction_returns_fresh_aggregate(client, monkeypatch):
    async def fake_toggle(session, *, event_id, user_id, kind):
        return True

    async def fake_counts(session, event_id):
        return {"like": 1}

    async def fake_mine(session, event_id, user_id):
        return ["like"]

    monkeypatch.setattr(repo, "toggle_reaction", fake_toggle)
    monkeypatch.setattr(repo, "reaction_counts", fake_counts)
    monkeypatch.setattr(repo, "reactions_of", fake_mine)

    resp = client.post(f"/events/{uuid.uuid4()}/reactions", json={"kind": "like"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] is True
    assert body["counts"] == {"like": 1}
    assert body["mine"] == ["like"]


def test_toggle_reaction_rejects_bad_kind_422(client):
    resp = client.post(f"/events/{uuid.uuid4()}/reactions", json={"kind": "love"})
    assert resp.status_code == 422  # caught by the Literal in the DTO


def test_cast_source_vote_shape(client, monkeypatch):
    src = uuid.uuid4()

    async def fake_cast(session, *, event_id, source_id, user_id, verdict, weight=1.0):
        return None

    async def fake_tallies(session, event_id):
        return {str(src): {"corroborate": 1}}

    monkeypatch.setattr(repo, "cast_source_vote", fake_cast)
    monkeypatch.setattr(repo, "source_vote_tallies", fake_tallies)
    # The trust-layer recompute is DB-backed (raw SQL); stub it for this wiring test.
    import chronos_core.validation_repo as vrepo

    async def _noop_async(*a, **k):
        return 0

    monkeypatch.setattr(vrepo, "recompute_source_quality", _noop_async)
    monkeypatch.setattr(vrepo, "recompute_event_confidence", _noop_async)
    monkeypatch.setattr(vrepo, "award_reputation", _noop_async)

    resp = client.post(
        f"/events/{uuid.uuid4()}/source-votes",
        json={"source_id": str(src), "verdict": "corroborate"},
    )
    assert resp.status_code == 200
    assert resp.json()["tallies"][str(src)] == {"corroborate": 1}


def test_create_link_attributes_to_actor(client, monkeypatch):
    captured = {}

    async def fake_add(session, *, src_event, dst_event, kind, user_id, weight=1.0):
        captured.update(user_id=user_id, kind=kind)
        return True

    monkeypatch.setattr(repo, "add_user_link", fake_add)
    a, b = uuid.uuid4(), uuid.uuid4()
    resp = client.post(
        "/links", json={"src_event": str(a), "dst_event": str(b)}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is True
    assert body["kind"] == "thematic"  # default
    assert captured["user_id"] == get_actor(None)


def test_remove_link_only_reports_removed(client, monkeypatch):
    async def fake_remove(session, *, src_event, dst_event, kind, user_id):
        return False

    monkeypatch.setattr(repo, "remove_user_link", fake_remove)
    resp = client.request(
        "DELETE",
        "/links",
        params={"src_event": str(uuid.uuid4()), "dst_event": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["removed"] is False


# --- notifications generation ---------------------------------------------------------


def test_like_notifies_the_event_author(client, monkeypatch):
    captured = {}

    async def fake_toggle(session, *, event_id, user_id, kind):
        return True  # reaction just added

    async def fake_notify_author(session, *, event_id, actor_id, kind):
        captured.update(event_id=event_id, actor_id=actor_id, kind=kind)

    monkeypatch.setattr(repo, "toggle_reaction", fake_toggle)
    monkeypatch.setattr(nrepo, "notify_event_author", fake_notify_author)
    ev = uuid.uuid4()
    resp = client.post(f"/events/{ev}/reactions", json={"kind": "like"})
    assert resp.status_code == 200
    assert captured == {"event_id": ev, "actor_id": get_actor(None), "kind": "like"}


def test_dislike_does_not_notify(client, monkeypatch):
    calls = []

    async def fake_toggle(session, *, event_id, user_id, kind):
        return True

    async def fake_notify_author(session, *, event_id, actor_id, kind):
        calls.append(kind)

    monkeypatch.setattr(repo, "toggle_reaction", fake_toggle)
    monkeypatch.setattr(nrepo, "notify_event_author", fake_notify_author)
    client.post(f"/events/{uuid.uuid4()}/reactions", json={"kind": "dislike"})
    assert calls == []  # only 'like' pings the author


def test_repost_notifies_the_event_author(client, monkeypatch):
    captured = {}

    async def fake_repost(session, *, user_id, event_id):
        return True

    async def fake_notify_author(session, *, event_id, actor_id, kind):
        captured.update(kind=kind)

    monkeypatch.setattr(srepo, "repost", fake_repost)
    monkeypatch.setattr(srepo, "record_activity", lambda *a, **k: _noop())
    monkeypatch.setattr(nrepo, "notify_event_author", fake_notify_author)
    resp = client.post(f"/events/{uuid.uuid4()}/repost")
    assert resp.status_code == 201
    assert captured.get("kind") == "repost"


async def _noop():
    return None


# --- repost ---------------------------------------------------------------------------


def test_repost_injects_actor_and_logs_share(client, monkeypatch):
    captured = {}

    async def fake_repost(session, *, user_id, event_id):
        captured.update(user_id=user_id, event_id=event_id)
        return True

    async def fake_record_activity(session, *, user_id, kind, target_type, target_id):
        captured.update(act_kind=kind, act_target=target_type)

    monkeypatch.setattr(srepo, "repost", fake_repost)
    monkeypatch.setattr(srepo, "record_activity", fake_record_activity)
    ev = uuid.uuid4()
    resp = client.post(f"/events/{ev}/repost")
    assert resp.status_code == 201
    assert resp.json() == {"event_id": str(ev), "reposted": True}
    assert captured["user_id"] == get_actor(None) and captured["event_id"] == ev
    # A repost is a public signal → logged as 'share' activity for the interest profile.
    assert captured["act_kind"] == "share" and captured["act_target"] == "event"


def test_unrepost_reports_post_state(client, monkeypatch):
    async def fake_unrepost(session, *, user_id, event_id):
        return True

    monkeypatch.setattr(srepo, "unrepost", fake_unrepost)
    ev = uuid.uuid4()
    resp = client.request("DELETE", f"/events/{ev}/repost")
    assert resp.status_code == 200
    assert resp.json() == {"event_id": str(ev), "reposted": False}


def test_repost_state_reports_reposted(client, monkeypatch):
    async def fake_is_reposted(session, *, user_id, event_id):
        return True

    monkeypatch.setattr(srepo, "is_reposted", fake_is_reposted)
    ev = uuid.uuid4()
    resp = client.get(f"/events/{ev}/repost/state")
    assert resp.status_code == 200
    assert resp.json()["reposted"] is True


# --- user-vs-agent link classification (the /related distinction) ---------------------


def test_link_origin_classifies_user_vs_agent():
    # A user id (UUID string) → user; an agent run label or None → agent.
    assert gq._link_origin(str(uuid.uuid4())) == "user"
    assert gq._link_origin("relate") == "agent"
    assert gq._link_origin(None) == "agent"
    assert gq._link_origin("") == "agent"
