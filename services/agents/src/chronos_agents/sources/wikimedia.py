"""Shared Wikimedia REST helpers — resolve a Wikipedia article's lead image and a real,
playable video clip (WebM) from the REST ``summary`` / ``media-list`` endpoints.

Lifted out of ``seed_iran_us.py`` so both the PoC seeder and the Wikipedia source adapter
reuse the exact same media resolution (clips-first, ADR-0023). Pure-ish: each helper takes an
injected ``httpx.AsyncClient`` (so callers control the User-Agent + connection lifetime and
tests can mock the transport with respx).

WebM-only on purpose: Wikimedia's other format (Ogg/Theora) won't play in most browsers, so
we skip it rather than attach an unplayable clip.
"""

from __future__ import annotations

import logging
from urllib.parse import unquote

import httpx

log = logging.getLogger("chronos.agents.sources.wikimedia")

# Wikimedia requires a descriptive User-Agent (a generic one gets 403'd).
USER_AGENT = "ChronosBot/0.1 (+https://github.com/Alobidat/NewTimeLine) source adapter"

_REST_BASE = "https://en.wikipedia.org/api/rest_v1/page"


def wiki_article(source_url: str) -> str | None:
    """Extract the article title from an en.wikipedia.org/wiki/<Title> URL."""
    marker = "/wiki/"
    if "wikipedia.org" not in source_url or marker not in source_url:
        return None
    return source_url.split(marker, 1)[1]


async def wiki_image(client: httpx.AsyncClient, source_url: str) -> str | None:
    """Resolve an event's lead image URL from its Wikipedia article (REST summary)."""
    title = wiki_article(source_url)
    if title is None:
        return None
    try:
        resp = await client.get(f"{_REST_BASE}/summary/{title}", timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        log.warning("no wiki summary for %s", unquote(title))
        return None
    img = (data.get("originalimage") or data.get("thumbnail") or {}).get("source")
    return img


def best_webm(item: dict) -> dict | None:
    """Pick the best browser-playable WebM source from a media-list video item.

    Wikimedia exposes the original plus transcodes; we want a ``video/webm`` (VP8/VP9 —
    what Chrome plays) and prefer the largest one up to ~640px so it stays light."""
    webms = [
        s for s in item.get("sources", [])
        if (s.get("mime") or "").startswith("video/webm") and s.get("url")
    ]
    if not webms:
        return None

    def width(s: dict) -> int:
        try:
            return int(s.get("width") or 0)
        except (TypeError, ValueError):
            return 0

    capped = [s for s in webms if width(s) <= 640]
    pool = capped or webms
    return max(pool, key=width)


async def wiki_video(
    client: httpx.AsyncClient, source_url: str
) -> tuple[str, str | None] | None:
    """Find a real, playable video clip for an event from its Wikipedia article.

    Uses the REST ``media-list`` endpoint (the same Wikimedia source as the lead image) and
    returns ``(url, caption)`` for the first article video that has a WebM rendition, or
    ``None``."""
    title = wiki_article(source_url)
    if title is None:
        return None
    try:
        resp = await client.get(f"{_REST_BASE}/media-list/{title}", timeout=15.0)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception:
        log.warning("no wiki media-list for %s", unquote(title))
        return None
    for item in items:
        if item.get("type") != "video":
            continue
        src = best_webm(item)
        if src is None:
            continue
        url = src["url"]
        if url.startswith("//"):
            url = "https:" + url
        caption = (item.get("caption") or {}).get("text")
        return url, caption
    return None
