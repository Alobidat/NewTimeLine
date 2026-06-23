"""Normalizers: raw feed/dataset items → a CandidateEvent (pure, testable).

No I/O, no LLM (Tier 1). Keeping these pure means we can unit-test the fiddly bits
(BC-year parsing, WKT parsing) without a network or DB. See docs/ai-agents.md §2.2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from chronos_core.domain.temporal import TimePrecision, datetime_to_t
from chronos_core.schemas.event import GeoPoint

_POINT_RE = re.compile(r"Point\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)", re.I)
# Wikidata times can carry a leading '-' (BC) and a 5+ digit year, e.g. -0044-03-15T...
_WD_TIME_RE = re.compile(r"^([+-]?)(\d{1,11})-(\d{2})-(\d{2})T")


@dataclass
class CandidateMedia:
    """A media URL found on a feed item (image/video/audio), pre-archival-decision.

    ``width``/``height``/``duration_s`` are captured when the source reports them so the
    client can pick a good rendition and a clip can be ranked ahead of images (ADR-0024)."""

    kind: str  # image | video | audio
    url: str
    mime: str | None = None
    width: int | None = None
    height: int | None = None
    duration_s: int | None = None
    caption: str | None = None


@dataclass
class CandidateEvent:
    """A normalized, ready-to-publish event plus its single source's metadata."""

    title: str
    t_start: float
    time_precision: TimePrecision
    source_url: str
    summary: str | None = None
    t_end: float | None = None
    instant: datetime | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    geo: GeoPoint | None = None
    source_title: str | None = None
    source_publisher: str | None = None
    source_published_at: datetime | None = None
    source_kind: str | None = None
    media: list[CandidateMedia] = field(default_factory=list)


# Extension → (kind, mime) fallback when a feed gives no MIME type.
_MEDIA_EXT = {
    "jpg": ("image", "image/jpeg"), "jpeg": ("image", "image/jpeg"),
    "png": ("image", "image/png"), "gif": ("image", "image/gif"),
    "webp": ("image", "image/webp"), "avif": ("image", "image/avif"),
    "mp4": ("video", "video/mp4"), "webm": ("video", "video/webm"),
    "mov": ("video", "video/quicktime"), "m4v": ("video", "video/mp4"),
    "mp3": ("audio", "audio/mpeg"), "m4a": ("audio", "audio/mp4"),
    "ogg": ("audio", "audio/ogg"),
}


def _classify_media(url: str, mime: str | None, medium: str | None) -> CandidateMedia | None:
    """Decide image/video/audio for one URL from its MIME, ``medium`` hint, or extension."""
    m = (mime or "").lower()
    if m.startswith("image/") or medium == "image":
        return CandidateMedia("image", url, mime or None)
    if m.startswith("video/") or medium == "video":
        return CandidateMedia("video", url, mime or None)
    if m.startswith("audio/") or medium == "audio":
        return CandidateMedia("audio", url, mime or None)
    ext = url.rsplit(".", 1)[-1].split("?")[0].lower() if "." in url else ""
    if ext in _MEDIA_EXT:
        kind, guessed = _MEDIA_EXT[ext]
        return CandidateMedia(kind, url, mime or guessed)
    return None


def extract_media(entry: dict, *, limit: int = 10) -> list[CandidateMedia]:
    """Pull image/video/audio URLs from a feed entry's media fields (pure, testable).

    Handles RSS/Atom ``media:content``, ``media:thumbnail``, ``enclosures``, and
    ``rel=enclosure`` links. Dedups by URL, preserves order, caps at ``limit``."""
    out: list[CandidateMedia] = []
    seen: set[str] = set()

    def consider(url, mime=None, medium=None):
        if not url or url in seen:
            return
        cm = _classify_media(url, mime, medium)
        if cm is not None:
            seen.add(url)
            out.append(cm)

    for mc in entry.get("media_content") or []:
        consider(mc.get("url"), mc.get("type"), mc.get("medium"))
    for mt in entry.get("media_thumbnail") or []:
        consider(mt.get("url"), None, "image")
    for enc in entry.get("enclosures") or []:
        consider(enc.get("href") or enc.get("url"), enc.get("type"))
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure":
            consider(link.get("href"), link.get("type"))
    return out[:limit]


def parse_point_wkt(wkt: str | None) -> GeoPoint | None:
    """Parse a 'Point(lon lat)' WKT string (Wikidata P625) into a GeoPoint."""
    if not wkt:
        return None
    m = _POINT_RE.search(wkt)
    if not m:
        return None
    return GeoPoint(lon=float(m.group(1)), lat=float(m.group(2)))


def parse_wikidata_time(value: str | None) -> tuple[int, int, int] | None:
    """Parse a Wikidata time literal into (year, month, day); year may be negative (BC)."""
    if not value:
        return None
    m = _WD_TIME_RE.match(value)
    if not m:
        return None
    sign, year, month, day = m.groups()
    y = int(year) * (-1 if sign == "-" else 1)
    # Wikidata uses month/day 00 for coarse precision; clamp to 1 for arithmetic.
    return (y, max(int(month), 1), max(int(day), 1))


def wikidata_time_to_t(year: int, month: int, day: int) -> float:
    """Convert a (possibly BC) Wikidata date to a fractional signed year.

    We do this arithmetically (not via datetime) so BC / deep years are representable.
    Month-level fraction is plenty for plotting historical events.
    """
    return year + (month - 1) / 12.0 + (day - 1) / 372.0


def normalize_rss(entry: dict, *, feed_publisher: str | None = None) -> CandidateEvent | None:
    """Normalize one RSS entry (a plain dict). Requires a title, link, and a date."""
    title = (entry.get("title") or "").strip()
    link = entry.get("link")
    published: datetime | None = entry.get("published")
    if not title or not link or published is None:
        return None
    return CandidateEvent(
        title=title,
        summary=(entry.get("summary") or None),
        t_start=datetime_to_t(published),
        time_precision=TimePrecision.DAY,
        instant=published,
        category="news",
        source_url=link,
        source_title=title,
        source_publisher=feed_publisher,
        source_published_at=published,
        source_kind="news",
        media=extract_media(entry),
    )


# ── ActivityPub (ActivityStreams 2.0 `Video`, e.g. PeerTube) ───────────────────────────────
#
# PeerTube — the fediverse's video platform — exposes every video as an AS2 ``Video`` object
# (content-negotiated with ``Accept: application/activity+json``). The playable file lives in
# the ``url`` array as ``Link`` objects (one per resolution: ``mediaType: video/mp4`` for the
# direct files, plus an ``application/x-mpegURL`` HLS playlist whose nested ``tag`` carries the
# per-resolution mp4 links). We map that object to the same CandidateEvent every other ingestor
# produces, with the best browser-playable clip as a hero video — so federated clips flow
# through the unchanged publish → media pipeline and land in the video-first feed.

_TAG_RE = re.compile(r"<[^>]+>")
# ISO-8601 duration, e.g. "PT1M3S" / "PT45S" / "P1DT2H".
_ISO_DUR_RE = re.compile(
    r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$", re.I
)


def strip_html(text: str | None) -> str | None:
    """Flatten an HTML fragment (PeerTube descriptions are HTML) to plain text."""
    if not text:
        return None
    out = re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()
    return out or None


def iso8601_duration_to_seconds(value) -> int | None:
    """Parse an ISO-8601 duration (``PT1M3S``) to whole seconds. Accepts a plain int/float too
    (some feeds report seconds directly). Returns None when unparseable/zero."""
    if isinstance(value, (int, float)):
        return int(value) or None
    if not isinstance(value, str):
        return None
    m = _ISO_DUR_RE.match(value.strip())
    if not m:
        return None
    days, hours, mins, secs = m.groups()
    total = (
        (int(days) * 86400 if days else 0)
        + (int(hours) * 3600 if hours else 0)
        + (int(mins) * 60 if mins else 0)
        + (int(float(secs)) if secs else 0)
    )
    return total or None


def _as2_links(url_field) -> list[dict]:
    """All AS2 ``Link`` dicts under an object's ``url`` (PeerTube nests the per-resolution mp4
    links inside an HLS link's ``tag`` array, so we descend one level)."""
    items = url_field if isinstance(url_field, list) else ([url_field] if url_field else [])
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append(it)
        nested = it.get("tag")
        if isinstance(nested, list):
            out.extend(t for t in nested if isinstance(t, dict))
    return out


def _href(link: dict) -> str | None:
    h = link.get("href") or link.get("id")
    return h if isinstance(h, str) and h else None


def _pick_clip(url_field, max_width: int) -> tuple[str, str, int | None, int | None] | None:
    """Best browser-playable clip from an AS2 ``url`` array → (mime, href, width, height).

    Prefer a direct **mp4** at the largest width ≤ ``max_width`` (plays in every browser's
    <video>); fall back to an HLS playlist (``.m3u8``) when no mp4 is offered."""
    mp4s: list[dict] = []
    hls: dict | None = None
    for link in _as2_links(url_field):
        href = _href(link)
        if not href:
            continue
        mt = (link.get("mediaType") or "").lower()
        path = href.split("?", 1)[0].lower()
        if mt == "video/mp4" or path.endswith(".mp4"):
            mp4s.append(link)
        elif mt in ("application/x-mpegurl", "application/vnd.apple.mpegurl") or path.endswith(".m3u8"):
            hls = hls or link
    if mp4s:
        def width(l: dict) -> int:
            return int(l.get("width") or l.get("height") or 0)

        under = [l for l in mp4s if 0 < width(l) <= max_width]
        chosen = max(under or mp4s, key=width)
        return ("video/mp4", _href(chosen), chosen.get("width"), chosen.get("height"))  # type: ignore[arg-type]
    if hls:
        return ("application/x-mpegURL", _href(hls), hls.get("width"), hls.get("height"))  # type: ignore[arg-type]
    return None


def _html_watch_url(url_field) -> str | None:
    """The human watch page (``mediaType: text/html``) for provenance / source-url dedup."""
    for link in _as2_links(url_field):
        if (link.get("mediaType") or "").lower() == "text/html":
            return _href(link)
    return None


def _as2_datetime(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _as2_hashtags(tag_field) -> list[str]:
    out: list[str] = []
    for t in tag_field if isinstance(tag_field, list) else []:
        if isinstance(t, dict) and (t.get("type") == "Hashtag") and t.get("name"):
            out.append(str(t["name"]).lstrip("#").strip())
    return [h for h in out if h]


def normalize_activitypub_video(
    obj: dict,
    *,
    instance_host: str | None = None,
    max_clip_width: int = 720,
    max_duration_s: int | None = None,
) -> CandidateEvent | None:
    """Normalize one AS2 ``Video`` object (PeerTube/fediverse) into a CandidateEvent.

    Requires a title and a playable clip URL. ``max_duration_s`` skips overly-long videos so the
    short-form feed stays clip-shaped. Pure: no I/O — the adapter does the fetching."""
    if not isinstance(obj, dict) or obj.get("type") != "Video":
        return None
    name = (obj.get("name") or "").strip()
    if not name:
        return None
    duration_s = iso8601_duration_to_seconds(obj.get("duration"))
    if max_duration_s and duration_s and duration_s > max_duration_s:
        return None
    clip = _pick_clip(obj.get("url"), max_clip_width)
    if clip is None:
        return None
    mime, href, width, height = clip
    obj_id = obj.get("id") if isinstance(obj.get("id"), str) else None
    source_url = _html_watch_url(obj.get("url")) or obj_id
    if not source_url:
        return None
    published = _as2_datetime(obj.get("published"))
    t_start = datetime_to_t(published or datetime.now(UTC))
    host = instance_host or urlparse(source_url).netloc or None
    cat = obj.get("category")
    category = (
        str(cat["name"]).strip().lower()
        if isinstance(cat, dict) and cat.get("name")
        else "video"
    )
    tags = [*_as2_hashtags(obj.get("tag")), "video", "fediverse"]
    return CandidateEvent(
        title=name[:140],
        summary=strip_html(obj.get("content") or obj.get("summary")),
        t_start=t_start,
        time_precision=TimePrecision.DAY,
        instant=published,
        category=category,
        tags=list(dict.fromkeys(tags))[:8],  # dedup, keep order
        source_url=source_url,
        source_title=name[:200],
        source_publisher=host,
        source_published_at=published,
        source_kind="fediverse",
        media=[
            CandidateMedia(
                kind="video", url=href, mime=mime,
                width=width, height=height, duration_s=duration_s, caption=name[:200],
            )
        ],
    )


def normalize_wikidata(row: dict) -> CandidateEvent | None:
    """Normalize one Wikidata SPARQL binding (already flattened to plain values)."""
    title = (row.get("label") or "").strip()
    parsed = parse_wikidata_time(row.get("time"))
    if not title or parsed is None:
        return None
    year, month, day = parsed
    # Source: prefer the Wikipedia article, else the Wikidata entity page.
    source_url = row.get("article") or row.get("event")
    if not source_url:
        return None
    return CandidateEvent(
        title=title,
        t_start=wikidata_time_to_t(year, month, day),
        time_precision=TimePrecision.DAY,
        category="history",
        geo=parse_point_wkt(row.get("coord")),
        source_url=source_url,
        source_title=title,
        source_publisher="Wikipedia" if row.get("article") else "Wikidata",
        source_kind="encyclopedia",
    )
