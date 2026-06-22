"""Unit tests for the media-quality helpers in ``sources.wikimedia`` (pure; fake transport).

Covers the resolution-floor behaviour added for ADR-0024: recovering a width from a thumb URL,
``wiki_image`` recording dimensions + honouring the floor, and ``commons_images`` filtering /
ranking by resolution.
"""

from __future__ import annotations

import pytest

from chronos_agents.sources import wikimedia as wm


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal async httpx stand-in: routes by URL to a canned payload."""

    def __init__(self, *, summary=None, commons=None):
        self._summary = summary
        self._commons = commons

    async def get(self, url, *, params=None, timeout=None):
        if "/summary/" in url:
            return _Resp(self._summary or {})
        return _Resp(self._commons or {"query": {"pages": {}}})


def test_width_from_thumb_url():
    u = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg/1280px-X.jpg"
    assert wm.width_from_thumb_url(u) == 1280
    assert wm.width_from_thumb_url("https://example.com/no-thumb.jpg") is None


@pytest.mark.asyncio
async def test_wiki_image_records_thumb_width_and_prefers_big_original():
    # Original below the floor → fall back to a wide thumb rendition, width recorded.
    small_original = {
        "originalimage": {"source": "https://x/orig.jpg", "width": 320, "height": 200},
        "thumbnail": {"source": "https://upload/thumb/1/12/X.jpg/240px-X.jpg"},
    }
    img = await wm.wiki_image(_FakeClient(summary=small_original), "https://en.wikipedia.org/wiki/X")
    assert img is not None and img.width == wm.DEFAULT_THUMB_WIDTH
    assert f"{wm.DEFAULT_THUMB_WIDTH}px-" in img.url

    # A big original is taken as-is with its real dimensions.
    big = {"originalimage": {"source": "https://x/big.jpg", "width": 2000, "height": 1500}}
    img2 = await wm.wiki_image(_FakeClient(summary=big), "https://en.wikipedia.org/wiki/X")
    assert img2.url == "https://x/big.jpg" and img2.width == 2000


@pytest.mark.asyncio
async def test_commons_images_filters_below_floor_and_ranks_by_width():
    pages = {
        "1": {"title": "File:Tiny.jpg",
              "imageinfo": [{"url": "https://u/tiny.jpg", "mime": "image/jpeg", "width": 320,
                             "height": 200, "extmetadata": {}}]},
        "2": {"title": "File:Big.jpg",
              "imageinfo": [{"url": "https://u/big.jpg", "mime": "image/jpeg", "width": 1600,
                             "height": 1000, "extmetadata": {}}]},
        "3": {"title": "File:Mid.jpg",
              "imageinfo": [{"url": "https://u/mid.jpg", "mime": "image/jpeg", "width": 800,
                             "height": 600, "extmetadata": {}}]},
    }
    out = await wm.commons_images(_FakeClient(commons={"query": {"pages": pages}}), "anything")
    # Tiny (320 < 640) is dropped; results ranked widest-first.
    assert [c.width for c in out] == [1600, 800]
    assert out[0].url == "https://u/big.jpg"
    assert out[0].page_url.startswith("https://commons.wikimedia.org/wiki/")
    assert "Big" in out[0].page_url
