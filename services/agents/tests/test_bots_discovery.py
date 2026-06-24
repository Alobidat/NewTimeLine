"""Unit tests for the new free-video providers in ``bots.discovery`` (pure; fake transport).

Covers the Internet Archive adapter (keyless: search → license gate → metadata → direct mp4)
and the Pixabay adapter (keyed: rendition selection), plus the ``licenseurl`` → license-string
mapping that the IA gate depends on. No network: a fake httpx client routes by URL to canned JSON.
"""

from __future__ import annotations

import pytest

from chronos_agents.bots import discovery as d
from chronos_agents.sources.licensing import is_free_license


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Routes GETs by URL substring to a canned payload (accepts the kwargs the adapters pass)."""

    def __init__(self, routes: dict):
        self._routes = routes

    async def get(self, url, *, params=None, timeout=None, headers=None):
        for needle, payload in self._routes.items():
            if needle in url:
                return _Resp(payload)
        raise AssertionError(f"unexpected URL: {url}")


# --- license mapping -------------------------------------------------------------------------


def test_ia_license_maps_free_urls():
    assert d._ia_license("https://creativecommons.org/licenses/by/3.0/") == "CC BY 3.0"
    assert d._ia_license("https://creativecommons.org/licenses/by-sa/4.0/") == "CC BY-SA 4.0"
    assert d._ia_license("https://creativecommons.org/publicdomain/mark/1.0/") == "Public Domain"
    assert d._ia_license("https://creativecommons.org/publicdomain/zero/1.0/") == "CC0"
    assert d._ia_license(None) is None
    # The mapped strings must satisfy / fail the actual gate the adapter applies.
    assert is_free_license("CC BY 3.0")
    assert is_free_license("CC BY-SA 4.0")
    assert is_free_license("CC0")
    assert is_free_license("Public Domain")


def test_ia_license_noncommercial_and_noderiv_are_rejected_by_gate():
    nc = d._ia_license("https://creativecommons.org/licenses/by-nc-sa/4.0/")
    nd = d._ia_license("https://creativecommons.org/licenses/by-nd/4.0/")
    assert nc == "CC BY-NC-SA 4.0" and not is_free_license(nc)
    assert nd == "CC BY-ND 4.0" and not is_free_license(nd)


def test_ia_year_and_int_helpers():
    assert d._ia_year("1917") == 1917.0
    assert d._ia_year("c. 1920s") == 1920.0
    assert d._ia_year(None) is None
    assert d._ia_int("720") == 720
    assert d._ia_int(None) is None


# --- Internet Archive adapter ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_builds_direct_url_and_drops_nonfree():
    search = {
        "response": {
            "docs": [
                {"identifier": "good_film", "title": "A Free Film",
                 "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                 "year": "1925", "creator": "Some Director"},
                {"identifier": "nc_film", "title": "Non-commercial",
                 "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"},
            ]
        }
    }
    meta = {
        "files": [
            {"name": "good_film_orig.mp4", "size": "90000000", "width": "1920", "height": "1080"},
            {"name": "good_film_512kb.mp4", "size": "5000000", "width": "640", "height": "360"},
            {"name": "good_film.png", "size": "1000"},
        ]
    }
    client = _FakeClient({"advancedsearch": search, "metadata/good_film": meta})
    clips = await d._archive(client, "cinema", limit=5, allow_nc=False)

    assert len(clips) == 1  # the NC item is gated out
    c = clips[0]
    # Smallest mp4 (the web derivative) is chosen, and the download URL is well-formed.
    assert c.url == "https://archive.org/download/good_film/good_film_512kb.mp4"
    assert c.source_url == "https://archive.org/details/good_film"
    assert c.provider == "archive" and c.mime == "video/mp4"
    assert c.license == "CC BY 4.0" and is_free_license(c.license)
    assert c.width == 640 and c.height == 360 and c.year == 1925.0


@pytest.mark.asyncio
async def test_archive_skips_items_with_no_playable_file():
    search = {"response": {"docs": [
        {"identifier": "audio_only",
         "licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/"},
    ]}}
    meta = {"files": [{"name": "track.mp3", "size": "100"}]}
    client = _FakeClient({"advancedsearch": search, "metadata/audio_only": meta})
    assert await d._archive(client, "q", limit=5, allow_nc=False) == []


# --- Pixabay adapter -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pixabay_picks_best_rendition_under_max_width():
    hits = {"hits": [{
        "pageURL": "https://pixabay.com/videos/id-123/",
        "tags": "ocean, waves, nature", "duration": 12, "user": "Photographer",
        "videos": {
            "large": {"url": "https://cdn/large.mp4", "width": 1920, "height": 1080},
            "medium": {"url": "https://cdn/medium.mp4", "width": 1280, "height": 720},
            "small": {"url": "https://cdn/small.mp4", "width": 640, "height": 360},
        },
    }]}
    client = _FakeClient({"pixabay.com/api/videos": hits})
    clips = await d._pixabay(client, "ocean", "fake-key", limit=5, max_width=720)

    assert len(clips) == 1
    c = clips[0]
    # max_width gates on pixel WIDTH: 640 ("small") is the only rendition at-or-under 720px wide
    # (medium is 1280w, large 1920w) — same rule as the Pexels adapter.
    assert c.url == "https://cdn/small.mp4" and c.width == 640 and c.height == 360
    assert c.provider == "pixabay" and "ocean" in c.title
    assert is_free_license(c.license)  # "Pixabay License (free)"


def test_pixabay_best_file_falls_back_to_smallest_when_all_over_width():
    videos = {
        "large": {"url": "https://cdn/large.mp4", "width": 3840, "height": 2160},
        "medium": {"url": "https://cdn/medium.mp4", "width": 1920, "height": 1080},
    }
    best = d._pixabay_best_file(videos, max_width=720)
    assert best["url"] == "https://cdn/medium.mp4"  # smallest available when none fit
    assert d._pixabay_best_file({}, max_width=720) is None
