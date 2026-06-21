"""Tests for the Phase-3c source adapters (event-presentation §6).

respx mocks httpx at the transport layer (same approach as test_geocode.py) so no real
network or DB is touched. The Wikipedia adapter parsing test exercises the full path:
search JSON → per-hit REST summary (lead image) + media-list (WebM clip) → CandidateEvent.
The registry enable/disable test drives enabled_adapters() through a tiny fake session.
"""

from __future__ import annotations

import httpx
import respx

from chronos_agents.sources import registry, wikimedia
from chronos_agents.sources.base import SubjectQuery
from chronos_agents.sources.wikipedia import WikipediaAdapter

_SEARCH = "https://en.wikipedia.org/w/api.php"
_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
_MEDIA = "https://en.wikipedia.org/api/rest_v1/page/media-list/"


@respx.mock
async def test_wikipedia_adapter_parses_hit_with_image_hero_and_webm_clip():
    respx.get(_SEARCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "query": {
                    "search": [
                        {
                            "title": "Assassination of Qasem Soleimani",
                            "snippet": "A US drone <span class=\"searchmatch\">strike</span> killed …",
                        }
                    ]
                }
            },
        )
    )
    respx.get(url__startswith=_SUMMARY).mock(
        return_value=httpx.Response(
            200,
            json={"originalimage": {
                "source": "https://upload.wikimedia.org/lead.jpg",
                "width": 1024, "height": 768,
            }},
        )
    )
    respx.get(url__startswith=_MEDIA).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "type": "video",
                        "caption": {"text": "Aftermath footage"},
                        "duration": 42,
                        "sources": [
                            {"mime": "video/webm", "url": "//upload.wikimedia.org/clip.webm",
                             "width": 480, "height": 360},
                            {"mime": "application/ogg", "url": "//upload.wikimedia.org/x.ogv",
                             "width": 720},
                        ],
                    }
                ]
            },
        )
    )

    out = await WikipediaAdapter().collect(SubjectQuery(keyword="Soleimani"), limit=5)

    assert len(out) == 1
    ev = out[0]
    assert ev.title == "Assassination of Qasem Soleimani"
    assert ev.source_url == "https://en.wikipedia.org/wiki/Assassination_of_Qasem_Soleimani"
    assert ev.source_kind == "encyclopedia"
    # snippet HTML stripped into the summary
    assert "searchmatch" not in (ev.summary or "")
    assert "strike" in (ev.summary or "")
    # media: clip FIRST (clips-first hero, ADR-0024), then the high-res image; Ogg skipped.
    kinds = [(m.kind, m.url) for m in ev.media]
    assert kinds[0] == ("video", "https://upload.wikimedia.org/clip.webm")
    assert ("image", "https://upload.wikimedia.org/lead.jpg") in kinds
    assert all(not m.url.endswith(".ogv") for m in ev.media)
    # dimensions + duration captured so the client can pick a rendition + rank the clip
    clip = next(m for m in ev.media if m.kind == "video")
    assert (clip.width, clip.height, clip.duration_s) == (480, 360, 42)
    assert clip.caption == "Aftermath footage"
    image = next(m for m in ev.media if m.kind == "image")
    assert (image.width, image.height) == (1024, 768)


@respx.mock
async def test_wikipedia_adapter_empty_search_yields_no_events():
    respx.get(_SEARCH).mock(
        return_value=httpx.Response(200, json={"query": {"search": []}})
    )
    out = await WikipediaAdapter().collect(SubjectQuery(keyword="zzznomatch"), limit=5)
    assert out == []


# --- registry enable/disable filtering (no network; fake session for config_service) ---


class _FakeRow:
    def __init__(self, value):
        self.value = value


class _FakeSession:
    """Minimal stand-in for AsyncSession.get(Config, key) used by config_service.get."""

    def __init__(self, values: dict):
        self._values = values

    async def get(self, _model, key):
        if key in self._values:
            return _FakeRow(self._values[key])
        return None


async def test_enabled_adapters_filters_by_config():
    # wikidata disabled, rss explicitly enabled, wikipedia unset (defaults True).
    session = _FakeSession(
        {
            "agents.ingest.rss.feeds": ["http://example.com/rss"],
            "agents.sources.wikidata.enabled": False,
            "agents.sources.rss.enabled": True,
        }
    )
    enabled = await registry.enabled_adapters(session)
    ids = {a.id for a in enabled}
    assert "wikidata" not in ids        # explicitly disabled → filtered out
    assert "wikipedia" in ids           # unset → default True
    assert "rss" in ids


# --- media quality helpers (ADR-0024): higher-res image, best clip + cap ---


def test_upscale_thumb_url_requests_a_wider_rendition():
    thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg/120px-X.jpg"
    bigger = wikimedia.upscale_thumb_url(thumb, target_width=1280)
    assert "/1280px-" in bigger and "/120px-" not in bigger
    # never shrinks an already-large rendition, and leaves non-thumb URLs untouched
    assert wikimedia.upscale_thumb_url(thumb.replace("120px", "2000px"), 1280).count("2000px") == 1
    assert wikimedia.upscale_thumb_url("https://example.com/orig.jpg", 1280) == \
        "https://example.com/orig.jpg"


@respx.mock
async def test_wiki_image_falls_back_to_upsized_thumbnail():
    # No originalimage → take the thumbnail but request a larger width (ADR-0024).
    respx.get(url__startswith=_SUMMARY).mock(
        return_value=httpx.Response(200, json={"thumbnail": {
            "source": "https://upload.wikimedia.org/thumb/a/ab/X.jpg/240px-X.jpg",
        }})
    )
    async with httpx.AsyncClient() as client:
        res = await wikimedia.wiki_image(
            client, "https://en.wikipedia.org/wiki/X", target_width=1280
        )
    assert res is not None and "/1280px-" in res.url


def test_best_webm_picks_largest_under_the_width_cap():
    item = {"sources": [
        {"mime": "video/webm", "url": "//w/240.webm", "width": 240},
        {"mime": "video/webm", "url": "//w/480.webm", "width": 480},
        {"mime": "video/webm", "url": "//w/1080.webm", "width": 1080},
        {"mime": "application/ogg", "url": "//w/x.ogv", "width": 720},
    ]}
    # cap 720 → 480 is the biggest webm at/under the cap; 1080 excluded, ogg never considered
    assert wikimedia.best_webm(item, max_width=720)["url"] == "//w/480.webm"
    # raising the cap lets the bigger (higher-quality) rendition through
    assert wikimedia.best_webm(item, max_width=2000)["url"] == "//w/1080.webm"


def test_best_webm_returns_none_without_a_playable_source():
    assert wikimedia.best_webm({"sources": [
        {"mime": "application/ogg", "url": "//w/x.ogv", "width": 720},
    ]}) is None


async def test_all_adapters_lists_every_source_with_wikipedia_first():
    session = _FakeSession({})
    adapters = await registry.all_adapters(session)
    ids = [a.id for a in adapters]
    assert ids[0] == "wikipedia"        # media-rich / clip-bearing listed first
    assert set(ids) == {"wikipedia", "wikidata", "rss"}
    assert await registry.get_adapter(session, "wikipedia") is not None
    assert await registry.get_adapter(session, "nope") is None
