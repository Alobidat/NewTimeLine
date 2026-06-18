"""Write helpers shared by the API and the agents (so event-write logic lives in one place).

Reads with PostGIS projections live in the API (chronos_api.queries); these are the
mutations: create an event, attach a source, refresh derived severity/confidence.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.domain.severity import (
    SeverityWeights,
    compute_severity,
    normalize_corroboration,
)
from chronos_core.domain.temporal import materialize_span
from chronos_core.models.event import Event
from chronos_core.models.source import EventSource, Source
from chronos_core.schemas.event import EventCreate, GeoPoint


def _point_expr(geo: GeoPoint | None):
    """SQL expression for a WGS84 point, or None."""
    if geo is None:
        return None
    return func.ST_SetSRID(func.ST_MakePoint(geo.lon, geo.lat), 4326)


def _derive_scores(source_count: int, weights: SeverityWeights | None):
    """Compute severity + confidence from current signals (Phase 1: corroboration only)."""
    sev = compute_severity(source_count=source_count, weights=weights)
    confidence = round(normalize_corroboration(source_count) * 100)
    return sev, confidence


async def create_event(
    session: AsyncSession,
    data: EventCreate,
    *,
    source_count: int = 0,
    weights: SeverityWeights | None = None,
) -> Event:
    """Insert an event, materializing ``t_end`` and derived scores. Caller commits."""
    t_start, t_end = materialize_span(data.t_start, data.time_precision, data.t_end)
    sev, confidence = _derive_scores(source_count, weights)
    event = Event(
        title=data.title,
        summary=data.summary,
        body=data.body,
        t_start=t_start,
        t_end=t_end,
        time_precision=data.time_precision,
        instant=data.instant,
        category=data.category,
        tags=data.tags,
        geom=_point_expr(data.geo),
        geo_label=data.geo_label,
        severity=sev.score,
        severity_breakdown={
            "impact": sev.impact,
            "social": sev.social,
            "corroboration": sev.corroboration,
        },
        confidence=confidence,
        source_count=source_count,
        created_by_agent=data.created_by_agent,
    )
    session.add(event)
    await session.flush()
    return event


async def get_or_create_source(
    session: AsyncSession,
    *,
    url: str,
    title: str | None = None,
    publisher: str | None = None,
    published_at=None,
    kind: str | None = None,
) -> Source:
    """Return the existing source for this URL's content hash, or create one."""
    content_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:64]
    existing = await session.scalar(
        select(Source).where(Source.content_hash == content_hash)
    )
    if existing is not None:
        return existing
    source = Source(
        url=url,
        domain=urlparse(url).netloc,
        title=title,
        publisher=publisher,
        published_at=published_at,
        content_hash=content_hash,
        kind=kind,
    )
    session.add(source)
    await session.flush()
    return source


async def link_source(
    session: AsyncSession,
    event: Event,
    source: Source,
    *,
    relation: str = "reports",
    added_by: str | None = None,
    weights: SeverityWeights | None = None,
) -> bool:
    """Attach a source to an event (idempotent). Bumps source_count + refreshes scores.

    Returns True if a new link was created.
    """
    exists = await session.get(EventSource, (event.id, source.id))
    if exists is not None:
        return False
    session.add(
        EventSource(
            event_id=event.id, source_id=source.id, relation=relation, added_by=added_by
        )
    )
    event.source_count += 1
    sev, confidence = _derive_scores(event.source_count, weights)
    event.severity = sev.score
    event.severity_breakdown = {
        "impact": sev.impact,
        "social": sev.social,
        "corroboration": sev.corroboration,
    }
    event.confidence = confidence
    return True
