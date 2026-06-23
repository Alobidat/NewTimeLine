"""Tests for publish.attach_media — clips-first hero + image quality floor (ADR-0024).

No DB: ``config_service.get`` and ``repository.discover_media`` are monkeypatched so we can
assert the (role, rank) and dimensions each media item is attached with.
"""

from __future__ import annotations

import pytest
from chronos_core import config_service, repository

from chronos_agents import publish
from chronos_agents.normalize import CandidateEvent, CandidateMedia

# Every test here is async; under asyncio STRICT mode each needs the marker (cf.
# test_wikimedia_quality.py). A module-level pytestmark applies it to all of them.
pytestmark = pytest.mark.asyncio


class _Event:
    id = "evt"


def _candidate(media: list[CandidateMedia]) -> CandidateEvent:
    return CandidateEvent(
        title="t", t_start=2020.0, time_precision=None, source_url="u",
        source_kind="encyclopedia", media=media,
    )


@pytest.fixture
def captured(monkeypatch):
    """Capture discover_media kwargs; default config (prefer_clips on, min width 200)."""
    calls: list[dict] = []

    async def fake_get(_session, key, default=None):
        return default

    async def fake_discover(session, event, **kw):
        calls.append(kw)

    monkeypatch.setattr(config_service, "get", fake_get)
    monkeypatch.setattr(repository, "discover_media", fake_discover)
    return calls


async def test_clip_is_hero_and_outranks_images(captured):
    cand = _candidate([
        CandidateMedia("image", "img.jpg", width=1024, height=768),
        CandidateMedia("video", "clip.webm", "video/webm", width=480, duration_s=30),
    ])
    await publish.attach_media(None, _Event(), cand, agent_name="x", source_id="s")

    by_url = {c["url"]: c for c in captured}
    assert by_url["clip.webm"]["role"] == "hero" and by_url["clip.webm"]["rank"] == 0
    assert by_url["img.jpg"]["role"] == "gallery"
    assert by_url["clip.webm"]["rank"] < by_url["img.jpg"]["rank"]
    # dimensions/duration are forwarded so the client can pick + the policy can rank
    assert by_url["clip.webm"]["duration_s"] == 30
    assert (by_url["img.jpg"]["width"], by_url["img.jpg"]["height"]) == (1024, 768)


async def test_image_is_hero_when_no_clip(captured):
    cand = _candidate([CandidateMedia("image", "img.jpg", width=900)])
    await publish.attach_media(None, _Event(), cand, agent_name="x", source_id="s")
    assert captured[0]["url"] == "img.jpg"
    assert captured[0]["role"] == "hero" and captured[0]["rank"] == 0


async def test_tiny_image_is_dropped_by_the_quality_floor(captured):
    # A known-tiny icon (40px) is below the 200px floor and must not be attached;
    # the unknown-width image and the real one survive.
    cand = _candidate([
        CandidateMedia("image", "icon.png", width=40),
        CandidateMedia("image", "real.jpg", width=1200),
        CandidateMedia("image", "unknown.jpg"),
    ])
    await publish.attach_media(None, _Event(), cand, agent_name="x", source_id="s")
    urls = {c["url"] for c in captured}
    assert "icon.png" not in urls
    assert {"real.jpg", "unknown.jpg"} <= urls
