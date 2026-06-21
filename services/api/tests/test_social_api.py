"""Router request/response-shape tests for the social / promote / feed / upload APIs
(Phase 4-B). No DB: ``get_session`` is overridden with a no-op fake and the repo/service
helpers are monkeypatched, so these assert the wiring — actor injection via the auth seam,
DTO serialization, status codes, required-metadata 400s — not persistence.
"""

from __future__ import annotations

import io
import uuid

import chronos_core.interest as interest
import chronos_core.social_repo as srepo
import chronos_core.upload as upload_core
import chronos_api.feed_queries as fq
import pytest
from chronos_api.auth_stub import get_actor, require_verified_actor
from chronos_api.deps import get_session
from chronos_api.routers import feed, social, upload
from chronos_core.schemas.event import EventRead
from chronos_core.schemas.social import FeedItem, FeedResponse, InterestProfile
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeSession:
    async def flush(self):
        return None


async def _fake_session():
    yield _FakeSession()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(social.router)
    app.include_router(feed.router)
    app.include_router(upload.router)
    app.dependency_overrides[get_session] = _fake_session
    # Stand in a fixed verified actor (the gate itself is unit-tested in test_auth.py).
    app.dependency_overrides[require_verified_actor] = get_actor
    return TestClient(app)


# --- follows --------------------------------------------------------------------------


def test_follow_injects_actor_and_records_activity(client, monkeypatch):
    captured = {}

    async def fake_follow(session, *, user_id, target_type, target_id):
        captured.update(user_id=user_id, target_type=target_type)
        return True

    async def fake_activity(session, *, user_id, kind, target_type, target_id, weight=None):
        captured["activity_kind"] = kind
        return None

    monkeypatch.setattr(srepo, "follow", fake_follow)
    monkeypatch.setattr(srepo, "record_activity", fake_activity)

    ent = uuid.uuid4()
    resp = client.post("/follow", params={"target_type": "entity", "target_id": str(ent)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["following"] is True
    assert captured["user_id"] == get_actor(None)
    assert captured["activity_kind"] == "follow"


def test_follow_self_returns_422(client, monkeypatch):
    async def fake_follow(session, *, user_id, target_type, target_id):
        raise ValueError("cannot follow yourself")

    monkeypatch.setattr(srepo, "follow", fake_follow)
    resp = client.post("/follow", params={"target_type": "user", "target_id": str(uuid.uuid4())})
    assert resp.status_code == 422


def test_follow_counts_shape(client, monkeypatch):
    async def fake_followers(session, *, target_type, target_id):
        return 5

    async def fake_following(session, *, user_id):
        return 3

    monkeypatch.setattr(srepo, "follower_count", fake_followers)
    monkeypatch.setattr(srepo, "following_count", fake_following)
    u = uuid.uuid4()
    resp = client.get("/follow/counts", params={"target_type": "user", "target_id": str(u)})
    assert resp.status_code == 200
    assert resp.json() == {
        "target_type": "user", "target_id": str(u), "followers": 5, "following": 3
    }


# --- promotes -------------------------------------------------------------------------


def test_cast_promote_returns_fresh_aggregate(client, monkeypatch):
    async def fake_cast(session, *, user_id, target_type, target_id, value):
        return value

    async def fake_tally(session, *, target_type, target_id):
        return (3, 4, 1)

    async def fake_activity(session, **kw):
        return None

    monkeypatch.setattr(srepo, "cast_promote", fake_cast)
    monkeypatch.setattr(srepo, "promote_tally", fake_tally)
    monkeypatch.setattr(srepo, "record_activity", fake_activity)

    resp = client.post(
        "/promote", json={"target_type": "relation", "target_id": str(uuid.uuid4()), "value": 1}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mine"] == 1 and body["score"] == 3 and body["up"] == 4 and body["down"] == 1


def test_cast_promote_rejects_bad_value_422(client):
    resp = client.post(
        "/promote", json={"target_type": "event", "target_id": str(uuid.uuid4()), "value": 9}
    )
    assert resp.status_code == 422  # caught by the Literal in the DTO


# --- interest -------------------------------------------------------------------------


def test_me_interests_shape(client, monkeypatch):
    async def fake_profile(session, actor, *, now=None):
        return InterestProfile(categories={"war": 2.0}, sample_size=4)

    monkeypatch.setattr(interest, "compute_profile", fake_profile)
    resp = client.get("/me/interests")
    assert resp.status_code == 200
    body = resp.json()
    assert body["categories"] == {"war": 2.0} and body["sample_size"] == 4


# --- feed -----------------------------------------------------------------------------


def _feed_resp(tab):
    ev = EventRead(
        id=uuid.uuid4(), title="t", t_start=2020.0, t_end=2020.0,
        time_precision="day", severity=0, confidence=0, source_count=0, status="published",
    )
    return FeedResponse(tab=tab, items=[FeedItem(event=ev, score=1.5)], next_cursor="o:10")


def test_feed_foryou_uses_profile_and_records_view(client, monkeypatch):
    seen = {}

    async def fake_profile(session, actor, *, now=None):
        return InterestProfile()

    async def fake_foryou(session, *, user_id, cursor, limit, profile=None):
        seen["profile"] = profile
        return _feed_resp("foryou")

    async def fake_activity(session, *, user_id, kind, target_type, target_id, weight=None):
        seen.setdefault("views", 0)
        seen["views"] += 1
        return None

    monkeypatch.setattr(interest, "compute_profile", fake_profile)
    monkeypatch.setattr(fq, "fetch_foryou", fake_foryou)
    monkeypatch.setattr(srepo, "record_activity", fake_activity)

    resp = client.get("/feed/foryou")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tab"] == "foryou" and body["next_cursor"] == "o:10"
    assert len(body["items"]) == 1 and body["items"][0]["score"] == 1.5
    assert seen["profile"] is not None and seen["views"] == 1


def test_feed_following_and_discover_dispatch(client, monkeypatch):
    async def fake_following(session, *, user_id, cursor, limit):
        return _feed_resp("following")

    async def fake_discover(session, *, user_id, cursor, limit):
        return _feed_resp("discover")

    async def fake_activity(session, **kw):
        return None

    monkeypatch.setattr(fq, "fetch_following", fake_following)
    monkeypatch.setattr(fq, "fetch_discover", fake_discover)
    monkeypatch.setattr(srepo, "record_activity", fake_activity)

    assert client.get("/feed/following").json()["tab"] == "following"
    assert client.get("/feed/discover").json()["tab"] == "discover"


def test_feed_unknown_tab_404(client):
    assert client.get("/feed/trending").status_code == 404


# --- upload ---------------------------------------------------------------------------


def _video():
    return ("clip.mp4", io.BytesIO(b"\x00\x01\x02fakevideo"), "video/mp4")


def test_upload_requires_metadata(client, monkeypatch):
    async def fake_cfg(session, key, default=None):
        return default

    monkeypatch.setattr("chronos_api.routers.upload.config_service.get", fake_cfg)

    # Missing actors / locations / links → 400 (not stored).
    resp = client.post(
        "/upload",
        data={"title": "My clip", "t_start": "2024.5"},
        files={"file": _video()},
    )
    assert resp.status_code == 400


def test_upload_happy_path_stores_and_creates_event(client, monkeypatch):
    created = {}

    async def fake_cfg(session, key, default=None):
        return default

    def fake_put(key, data, *, content_type=None):
        created["key"] = key
        created["bytes"] = len(data)
        return key

    class _Ev:
        id = uuid.uuid4()

        class _S:
            value = "pending"

        status = _S()

    async def fake_create(session, **kw):
        created.update(kw)
        return _Ev()

    monkeypatch.setattr("chronos_api.routers.upload.config_service.get", fake_cfg)
    monkeypatch.setattr("chronos_api.routers.upload.objectstore.put_bytes", fake_put)
    monkeypatch.setattr(upload_core, "create_video_event", fake_create)
    # Don't touch Redis in the test.
    monkeypatch.setattr("chronos_api.routers.upload._enqueue_geocode", lambda: None)

    ev_link = str(uuid.uuid4())
    resp = client.post(
        "/upload",
        data={
            "title": "My clip", "t_start": "2024.5",
            "actors": "Alice, Bob", "locations": "Cairo", "links": ev_link,
        },
        files={"file": _video()},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["moderation"] == "pending"
    assert created["key"].startswith("uploads/")
    assert created["actor_names"] == ["Alice", "Bob"]
    assert created["location_names"] == ["Cairo"]
    assert [str(x) for x in created["link_event_ids"]] == [ev_link]
    assert created["user_id"] == get_actor(None)


def test_upload_from_source_url_when_no_file(client, monkeypatch):
    """The no-file-picker path: the clip is fetched server-side from `source_url`."""
    created = {}

    async def fake_cfg(session, key, default=None):
        return default

    async def fake_fetch(url, max_bytes):
        created["fetched_url"] = url
        return b"\x00\x01fakevideo", "video/mp4"

    def fake_put(key, data, *, content_type=None):
        created["key"] = key
        return key

    class _Ev:
        id = uuid.uuid4()

        class _S:
            value = "pending"

        status = _S()

    async def fake_create(session, **kw):
        created.update(kw)
        return _Ev()

    monkeypatch.setattr("chronos_api.routers.upload.config_service.get", fake_cfg)
    monkeypatch.setattr("chronos_api.routers.upload._fetch_source", fake_fetch)
    monkeypatch.setattr("chronos_api.routers.upload.objectstore.put_bytes", fake_put)
    monkeypatch.setattr(upload_core, "create_video_event", fake_create)
    monkeypatch.setattr("chronos_api.routers.upload._enqueue_geocode", lambda: None)

    resp = client.post(
        "/upload",
        data={
            "title": "Remote clip", "t_start": "2024.0",
            "actors": "Alice", "locations": "Cairo", "links": str(uuid.uuid4()),
            "source_url": "https://example.com/clip.mp4",
        },
    )
    assert resp.status_code == 201
    assert created["fetched_url"] == "https://example.com/clip.mp4"
    assert created["key"].startswith("uploads/")


def test_upload_without_file_or_source_url_is_400(client, monkeypatch):
    async def fake_cfg(session, key, default=None):
        return default

    monkeypatch.setattr("chronos_api.routers.upload.config_service.get", fake_cfg)
    resp = client.post(
        "/upload",
        data={"title": "x", "t_start": "1.0", "actors": "A", "locations": "B",
              "links": str(uuid.uuid4())},
    )
    assert resp.status_code == 400


def test_upload_rejects_bad_content_type(client, monkeypatch):
    async def fake_cfg(session, key, default=None):
        if key == "upload.allowed_mime":
            return ["video/mp4"]
        return default

    monkeypatch.setattr("chronos_api.routers.upload.config_service.get", fake_cfg)
    resp = client.post(
        "/upload",
        data={"title": "x", "t_start": "1.0", "actors": "A", "locations": "B",
              "links": str(uuid.uuid4())},
        files={"file": ("a.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert resp.status_code == 415
