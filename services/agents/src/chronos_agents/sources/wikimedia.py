"""Shared Wikimedia REST helpers — resolve a Wikipedia article's lead image and a real,
playable video clip (WebM) from the REST ``summary`` / ``media-list`` endpoints.

Lifted out of ``seed_iran_us.py`` so both the PoC seeder and the Wikipedia source adapter
reuse the exact same media resolution (clips-first, ADR-0023). Pure-ish: each helper takes an
injected ``httpx.AsyncClient`` (so callers control the User-Agent + connection lifetime and
tests can mock the transport with respx).

Quality (ADR-0024): we prefer the **highest-resolution** still image we can get (the
``originalimage`` over a thumbnail; for Wikimedia thumb URLs we request a wider rendition),
and the **largest browser-playable** clip up to a sane cap, capturing width/height/duration so
the client can pick well and rank a clip ahead of images for the hero.

WebM-only on purpose: Wikimedia's other format (Ogg/Theora) won't play in most browsers, so
we skip it rather than attach an unplayable clip.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

import httpx

log = logging.getLogger("chronos.agents.sources.wikimedia")

# Wikimedia requires a descriptive User-Agent (a generic one gets 403'd).
USER_AGENT = "ChronosBot/0.1 (+https://github.com/Alobidat/NewTimeLine) source adapter"

_REST_BASE = "https://en.wikipedia.org/api/rest_v1/page"

# Default browser-playable clip width cap (kept light; overridable per call from config).
DEFAULT_MAX_CLIP_WIDTH = 720
# Target width we upsize a Wikimedia *thumbnail* URL to when no original is available.
DEFAULT_THUMB_WIDTH = 1280

# A Wikimedia thumbnail URL embeds the rendition width as ``/<NNNpx->-<File>``. We rewrite
# that token to request a larger rendition (still served by Wikimedia, no extra round-trip).
_THUMB_WIDTH_RE = re.compile(r"/(\d+)px-")


@dataclass(frozen=True)
class ImageResult:
    """A resolved still image: its URL plus pixel dimensions when Wikimedia reports them."""

    url: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class VideoResult:
    """A resolved, browser-playable clip: URL + caption + dimensions + duration (seconds)."""

    url: str
    caption: str | None = None
    width: int | None = None
    height: int | None = None
    duration_s: int | None = None


_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
# Browser-playable container types we accept from Commons (Ogg/Theora is skipped — see header).
_PLAYABLE_VIDEO_MIME = {"video/webm", "video/mp4"}
# Skip clips whose binary is larger than this — /media/raw proxy-fetches them into memory.
_MAX_CLIP_BYTES = 80 * 1024 * 1024
_YEAR_RE = re.compile(r"(\d{4})")


@dataclass(frozen=True)
class CommonsVideo:
    """A freely-licensed Commons video file: direct URL + display/provenance metadata."""

    url: str            # direct upload.wikimedia.org file URL (browser-playable)
    page_url: str       # the Commons ``File:`` description page (used as the event source)
    title: str          # human title (filename, de-prefixed/de-extensioned)
    mime: str
    width: int | None = None
    height: int | None = None
    duration_s: int | None = None
    year: float | None = None   # parsed from DateTimeOriginal, when present
    description: str | None = None
    license: str | None = None
    credit: str | None = None


def _clean_title(file_title: str) -> str:
    """``File:Restored Apollo 11 Moonwalk.webm`` → ``Restored Apollo 11 Moonwalk``."""
    name = re.sub(r"^File:", "", file_title)
    name = re.sub(r"\.[A-Za-z0-9]+$", "", name)          # drop the extension
    name = name.replace("_", " ").strip()
    return name


def _meta(extmeta: dict, key: str) -> str | None:
    raw = (extmeta.get(key) or {}).get("value")
    if not raw:
        return None
    # extmetadata values are often small HTML fragments; strip tags for plain text.
    return re.sub(r"<[^>]+>", "", str(raw)).strip() or None


async def commons_videos(
    client: httpx.AsyncClient,
    query: str,
    *,
    limit: int = 10,
    max_width: int = DEFAULT_MAX_CLIP_WIDTH,
) -> list[CommonsVideo]:
    """Search Wikimedia Commons for browser-playable video files matching ``query``.

    Commons is a durable, CORS-friendly host of freely-licensed (CC / public-domain) media —
    unlike YouTube/TikTok/Instagram, whose clips can't be served to ``video_player`` and whose
    terms forbid download. Returns up to ``limit`` :class:`CommonsVideo` (WebM/MP4 only, under a
    size cap), newest-search-rank first. Best-effort: any transport/parse error yields ``[]``."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"{query} filetype:video",
        "gsrnamespace": "6",          # the File: namespace
        "gsrlimit": str(min(limit * 3, 50)),  # over-fetch; we filter by mime/size below
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiextmetadatafilter": "DateTimeOriginal|ImageDescription|LicenseShortName|Artist",
    }
    try:
        resp = await client.get(_COMMONS_API, params=params, timeout=20.0)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
    except Exception:
        log.warning("commons video search failed for %r", query)
        return []

    out: list[CommonsVideo] = []
    for page in pages.values():
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            continue
        mime = info.get("mime")
        if mime not in _PLAYABLE_VIDEO_MIME:
            continue
        if (info.get("size") or 0) > _MAX_CLIP_BYTES:
            continue
        w = _as_int(info.get("width"))
        if w and w < 320:                          # skip thumbnail-sized clips
            continue
        if w and max_width and w > max_width * 3:  # skip very large renditions
            continue
        extmeta = info.get("extmetadata") or {}
        year = None
        dto = _meta(extmeta, "DateTimeOriginal")
        if dto:
            m = _YEAR_RE.search(dto)
            if m:
                year = float(m.group(1))
        file_title = page.get("title", "")
        out.append(
            CommonsVideo(
                url=info["url"],
                page_url=f"https://commons.wikimedia.org/wiki/{quote(file_title.replace(' ', '_'))}",
                title=_clean_title(file_title),
                mime=mime,
                width=w,
                height=_as_int(info.get("height")),
                duration_s=_as_int(info.get("duration")),
                year=year,
                description=_meta(extmeta, "ImageDescription"),
                license=_meta(extmeta, "LicenseShortName"),
                credit=_meta(extmeta, "Artist"),
            )
        )
        if len(out) >= limit:
            break
    return out


def wiki_article(source_url: str) -> str | None:
    """Extract the article title from an en.wikipedia.org/wiki/<Title> URL."""
    marker = "/wiki/"
    if "wikipedia.org" not in source_url or marker not in source_url:
        return None
    return source_url.split(marker, 1)[1]


def upscale_thumb_url(url: str, target_width: int = DEFAULT_THUMB_WIDTH) -> str:
    """Rewrite a Wikimedia ``/NNNpx-`` thumbnail URL to request a wider rendition.

    Only enlarges (never shrinks) and only touches Wikimedia thumb URLs; any other URL is
    returned unchanged. This gives a higher-res image without an extra API call (ADR-0024).
    """
    m = _THUMB_WIDTH_RE.search(url)
    if not m:
        return url
    current = int(m.group(1))
    if current >= target_width:
        return url
    return _THUMB_WIDTH_RE.sub(f"/{target_width}px-", url, count=1)


async def wiki_image(
    client: httpx.AsyncClient, source_url: str, *, target_width: int = DEFAULT_THUMB_WIDTH
) -> ImageResult | None:
    """Resolve an event's lead image from its Wikipedia article (REST summary).

    Prefers the full-resolution ``originalimage``; falls back to the article ``thumbnail``
    but upsizes its Wikimedia thumb URL to ``target_width`` so we attach a decent image
    rather than a tiny one (ADR-0024). Returns ``None`` when there's no usable image.
    """
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

    original = data.get("originalimage") or {}
    thumb = data.get("thumbnail") or {}
    if original.get("source"):
        return ImageResult(
            url=original["source"],
            width=_as_int(original.get("width")),
            height=_as_int(original.get("height")),
        )
    src = thumb.get("source")
    if not src:
        return None
    # Upsizing the thumb URL means we no longer know the exact returned dimensions; leave
    # them unset (the media-fetcher fills real dimensions when it downloads the binary).
    return ImageResult(url=upscale_thumb_url(src, target_width))


def best_webm(item: dict, *, max_width: int = DEFAULT_MAX_CLIP_WIDTH) -> dict | None:
    """Pick the best browser-playable WebM source from a media-list video item.

    Wikimedia exposes the original plus transcodes; we want a ``video/webm`` (VP8/VP9 —
    what Chrome plays) and prefer the **largest** one up to ``max_width`` so it's as
    high-res as is reasonable while staying light (ADR-0024)."""
    webms = [
        s for s in item.get("sources", [])
        if (s.get("mime") or "").startswith("video/webm") and s.get("url")
    ]
    if not webms:
        return None

    def width(s: dict) -> int:
        return _as_int(s.get("width")) or 0

    capped = [s for s in webms if width(s) <= max_width]
    pool = capped or webms
    return max(pool, key=width)


async def wiki_video(
    client: httpx.AsyncClient, source_url: str, *, max_width: int = DEFAULT_MAX_CLIP_WIDTH
) -> VideoResult | None:
    """Find a real, playable video clip for an event from its Wikipedia article.

    Uses the REST ``media-list`` endpoint (the same Wikimedia source as the lead image) and
    returns a :class:`VideoResult` for the first article video that has a WebM rendition
    (largest up to ``max_width``), capturing dimensions + duration, or ``None``."""
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
        src = best_webm(item, max_width=max_width)
        if src is None:
            continue
        url = src["url"]
        if url.startswith("//"):
            url = "https:" + url
        caption = (item.get("caption") or {}).get("text")
        return VideoResult(
            url=url,
            caption=caption,
            width=_as_int(src.get("width")),
            height=_as_int(src.get("height")),
            duration_s=_as_int(item.get("duration") or src.get("duration")),
        )
    return None


def _as_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
