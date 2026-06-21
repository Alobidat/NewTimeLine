"""Tests for the Phase-3c source adapters (event-presentation §6).

respx mocks httpx at the transport layer (same approach as test_geocode.py) so no real
network or DB is touched. The Wikipedia adapter parsing test exercises the full path:
search JSON → per-hit REST summary (lead image) + media-list (WebM clip) → CandidateEvent.
The registry enable/disable test drives enabled_adapters() through a tiny fake session.
"""

from __future__ import annotations

import httpx
import respx

from chronos_agents.sources import registry
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
            json={"originalimage": {"source": "https://upload.wikimedia.org/lead.jpg"}},
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
                        "sources": [
                            {"mime": "video/webm", "url": "//upload.wikimedia.org/clip.webm",
                             "width": 480},
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
    # media: first is the image hero, then the WebM clip (https-normalized, Ogg skipped)
    kinds = [(m.kind, m.url) for m in ev.media]
    assert kinds[0] == ("image", "https://upload.wikimedia.org/lead.jpg")
    assert ("video", "https://upload.wikimedia.org/clip.webm") in kinds
    assert all(not m.url.endswith(".ogv") for m in ev.media)


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


async def test_all_adapters_lists_every_source_with_wikipedia_first():
    session = _FakeSession({})
    adapters = await registry.all_adapters(session)
    ids = [a.id for a in adapters]
    assert ids[0] == "wikipedia"        # media-rich / clip-bearing listed first
    assert set(ids) == {"wikipedia", "wikidata", "rss"}
    assert await registry.get_adapter(session, "wikipedia") is not None
    assert await registry.get_adapter(session, "nope") is None
