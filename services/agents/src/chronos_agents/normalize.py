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
