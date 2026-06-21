"""Normalizers: raw feed/dataset items → a CandidateEvent (pure, testable).

No I/O, no LLM (Tier 1). Keeping these pure means we can unit-test the fiddly bits
(BC-year parsing, WKT parsing) without a network or DB. See docs/ai-agents.md §2.2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

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
