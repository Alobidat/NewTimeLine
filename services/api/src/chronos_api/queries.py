"""Read queries for the timeline/map/detail endpoints.

Geometry is projected to a representative lon/lat (centroid) here so DTOs stay simple. The
timeline endpoint returns individual events when the window is sparse, or aggregated buckets
when dense (docs/architecture.md §4.2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chronos_core.schemas.event import (
    EventDetail,
    EventRead,
    EventReferenceRead,
    GeoPoint,
    SourceRead,
)
from chronos_core.schemas.entity import EntityRead
from chronos_core.schemas.timeline import (
    SummaryPlace,
    SummaryRep,
    TimelineBucket,
    TimelineResponse,
    TimelineSummary,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Caps that keep the summary payload bounded no matter how many events match.
_SUMMARY_TOP_ENTITIES = 8
_SUMMARY_TOP_PLACES = 8
_SUMMARY_REPS = 12

# Shared projection: an event row + representative point (centroid) as lon/lat.
_EVENT_COLS = """
    id, title, summary, t_start, t_end, time_precision, instant, category, tags,
    severity, confidence, source_count, geo_label, status, visibility,
    CASE WHEN geom IS NOT NULL THEN ST_X(ST_Centroid(geom)) END AS lon,
    CASE WHEN geom IS NOT NULL THEN ST_Y(ST_Centroid(geom)) END AS lat
"""


def _geo(row) -> GeoPoint | None:
    return GeoPoint(lon=row.lon, lat=row.lat) if row.lon is not None else None


def _event_read(row) -> EventRead:
    return EventRead(
        id=row.id,
        title=row.title,
        summary=row.summary,
        t_start=row.t_start,
        t_end=row.t_end,
        time_precision=row.time_precision,
        instant=row.instant,
        category=row.category,
        tags=list(row.tags or []),
        severity=row.severity,
        confidence=row.confidence,
        source_count=row.source_count,
        geo=_geo(row),
        geo_label=row.geo_label,
        status=row.status,
        # Projections that don't select these default safely (visibility→public, author→None).
        visibility=str(getattr(row, "visibility", "public") or "public"),
        author_id=getattr(row, "author_id", None),
    )


@dataclass
class TimelineParams:
    """Inputs for a timeline window request."""

    t0: float
    t1: float
    bbox: tuple[float, float, float, float] | None = None  # minlon,minlat,maxlon,maxlat
    category: str | None = None
    min_severity: int = 0
    max_events: int = 500  # above this, switch to buckets
    buckets: int = 200


def _filters(p: TimelineParams) -> tuple[str, dict]:
    """Build the shared WHERE clause + bind params for window/bucket queries."""
    clauses = ["status = 'published'", "t_start <= :t1", "t_end >= :t0"]
    params: dict = {"t0": p.t0, "t1": p.t1}
    if p.category:
        clauses.append("category = :category")
        params["category"] = p.category
    if p.min_severity:
        clauses.append("severity >= :min_severity")
        params["min_severity"] = p.min_severity
    if p.bbox:
        clauses.append(
            "geom IS NOT NULL AND ST_Intersects(geom, "
            "ST_MakeEnvelope(:minlon, :minlat, :maxlon, :maxlat, 4326))"
        )
        params |= dict(
            zip(("minlon", "minlat", "maxlon", "maxlat"), p.bbox, strict=True)
        )
    return " AND ".join(clauses), params


async def fetch_timeline(session: AsyncSession, p: TimelineParams) -> TimelineResponse:
    """Return events (sparse window) or aggregated buckets (dense window)."""
    if p.t1 <= p.t0:
        return TimelineResponse(mode="events", t0=p.t0, t1=p.t1)

    where, params = _filters(p)
    total = await session.scalar(text(f"SELECT count(*) FROM events WHERE {where}"), params)

    if (total or 0) <= p.max_events:
        rows = (
            await session.execute(
                text(
                    f"SELECT {_EVENT_COLS} FROM events WHERE {where} "
                    "ORDER BY t_start LIMIT :max_events"
                ),
                params | {"max_events": p.max_events},
            )
        ).all()
        return TimelineResponse(
            mode="events", t0=p.t0, t1=p.t1, events=[_event_read(r) for r in rows]
        )

    # Dense: aggregate into fixed-width buckets along the numeric-year axis.
    width = (p.t1 - p.t0) / p.buckets
    rows = (
        await session.execute(
            text(
                f"SELECT floor((t_start - :t0) / :w) AS b, count(*) AS c, "
                f"max(severity) AS m FROM events WHERE {where} GROUP BY b ORDER BY b"
            ),
            params | {"w": width},
        )
    ).all()
    buckets = [
        TimelineBucket(
            t_start=p.t0 + int(r.b) * width,
            t_end=p.t0 + (int(r.b) + 1) * width,
            count=r.c,
            peak_severity=r.m or 0,
        )
        for r in rows
    ]
    return TimelineResponse(
        mode="buckets", t0=p.t0, t1=p.t1, bucket_years=width, buckets=buckets
    )


async def fetch_timeline_summary(
    session: AsyncSession, p: TimelineParams
) -> TimelineSummary:
    """Distill a timeframe (+ optional bbox) into a fixed-size payload.

    Everything is aggregated server-side: a bounded set of buckets, top entities, top
    places, and a capped handful of representative events. We never stream the raw events
    of a dense window to the client — that is the whole point of this endpoint."""
    if p.t1 <= p.t0:
        return TimelineSummary(t0=p.t0, t1=p.t1, total=0)

    where, params = _filters(p)
    total = await session.scalar(
        text(f"SELECT count(*) FROM events WHERE {where}"), params
    )

    # Heatline buckets (same fixed-width aggregation as the dense timeline branch).
    width = (p.t1 - p.t0) / p.buckets
    bucket_rows = (
        await session.execute(
            text(
                f"SELECT floor((t_start - :t0) / :w) AS b, count(*) AS c, "
                f"max(severity) AS m FROM events WHERE {where} GROUP BY b ORDER BY b"
            ),
            params | {"w": width},
        )
    ).all()
    buckets = [
        TimelineBucket(
            t_start=p.t0 + int(r.b) * width,
            t_end=p.t0 + (int(r.b) + 1) * width,
            count=r.c,
            peak_severity=r.m or 0,
        )
        for r in bucket_rows
    ]

    # Top entities by event count in the window. The matched-ids CTE keeps the shared
    # event WHERE (unqualified columns) unambiguous despite the entity join.
    entity_rows = (
        await session.execute(
            text(
                f"WITH matched AS (SELECT id AS eid FROM events WHERE {where}) "
                "SELECT en.id, en.kind, en.name, en.external_id, "
                "CASE WHEN en.geom IS NOT NULL THEN ST_X(en.geom) END AS lon, "
                "CASE WHEN en.geom IS NOT NULL THEN ST_Y(en.geom) END AS lat, "
                "count(*) AS event_count FROM matched m "
                "JOIN event_entities ee ON ee.event_id = m.eid "
                "JOIN entities en ON en.id = ee.entity_id "
                "GROUP BY en.id ORDER BY event_count DESC, en.name LIMIT :lim"
            ),
            params | {"lim": _SUMMARY_TOP_ENTITIES},
        )
    ).all()
    top_entities = [
        EntityRead(
            id=r.id,
            kind=r.kind,
            name=r.name,
            external_id=r.external_id,
            geo=_geo(r),
            event_count=r.event_count,
        )
        for r in entity_rows
    ]

    # Top places by event count, with a representative centroid (avg of event centroids).
    place_rows = (
        await session.execute(
            text(
                f"SELECT geo_label AS label, count(*) AS c, "
                "avg(CASE WHEN geom IS NOT NULL THEN ST_X(ST_Centroid(geom)) END) AS lon, "
                "avg(CASE WHEN geom IS NOT NULL THEN ST_Y(ST_Centroid(geom)) END) AS lat "
                f"FROM events WHERE {where} AND geo_label IS NOT NULL "
                "GROUP BY geo_label ORDER BY c DESC, label LIMIT :lim"
            ),
            params | {"lim": _SUMMARY_TOP_PLACES},
        )
    ).all()
    top_places = [
        SummaryPlace(label=r.label, count=r.c, lat=r.lat, lon=r.lon) for r in place_rows
    ]

    # A capped set of high-impact representatives for the montage/headlines. Impact mixes
    # severity with source weight (ln(+2) so severity always contributes even at 0 sources).
    rep_rows = (
        await session.execute(
            text(
                f"WITH matched AS (SELECT id AS eid FROM events WHERE {where}) "
                f"SELECT {_EVENT_COLS}, "
                "(SELECT em.media_id FROM event_media em WHERE em.event_id = events.id "
                " AND em.role = 'hero' ORDER BY em.rank LIMIT 1) AS hero_media_id "
                "FROM events JOIN matched m ON m.eid = events.id "
                "ORDER BY severity * ln(source_count + 2.0) DESC, severity DESC, t_start "
                "LIMIT :lim"
            ),
            params | {"lim": _SUMMARY_REPS},
        )
    ).all()
    representatives = [
        SummaryRep(
            id=r.id,
            title=r.title,
            t_start=r.t_start,
            time_precision=r.time_precision,
            severity=r.severity,
            geo=_geo(r),
            geo_label=r.geo_label,
            hero_media_id=r.hero_media_id,
        )
        for r in rep_rows
    ]

    return TimelineSummary(
        t0=p.t0,
        t1=p.t1,
        total=total or 0,
        bucket_years=width,
        buckets=buckets,
        top_entities=top_entities,
        top_places=top_places,
        representatives=representatives,
    )


async def fetch_map(
    session: AsyncSession,
    bbox: tuple[float, float, float, float],
    t0: float,
    t1: float,
    min_severity: int = 0,
    limit: int = 1000,
) -> list[EventRead]:
    """Geolocated events within a viewport bbox + time window, heaviest first."""
    p = TimelineParams(t0=t0, t1=t1, bbox=bbox, min_severity=min_severity)
    where, params = _filters(p)
    rows = (
        await session.execute(
            text(
                f"SELECT {_EVENT_COLS} FROM events WHERE {where} "
                "ORDER BY severity DESC, t_start LIMIT :limit"
            ),
            params | {"limit": limit},
        )
    ).all()
    return [_event_read(r) for r in rows]


async def fetch_subtimeline(
    session: AsyncSession, event_id: uuid.UUID
) -> list[EventReferenceRead]:
    """The deep-time subject references for an event, ordered along the subject axis."""
    rows = (
        await session.execute(
            text(
                "SELECT id, label, t_start, t_end, subject_precision, detail, confidence, "
                "subject_event_id, "
                "CASE WHEN subject_geom IS NOT NULL "
                "THEN ST_X(ST_Centroid(subject_geom)) END AS lon, "
                "CASE WHEN subject_geom IS NOT NULL "
                "THEN ST_Y(ST_Centroid(subject_geom)) END AS lat "
                "FROM event_references WHERE event_id = :id ORDER BY t_start"
            ),
            {"id": event_id},
        )
    ).all()
    return [
        EventReferenceRead(
            id=r.id,
            label=r.label,
            t_start=r.t_start,
            t_end=r.t_end,
            subject_precision=r.subject_precision,
            detail=r.detail,
            confidence=r.confidence,
            subject_event_id=r.subject_event_id,
            geo=_geo(r),
        )
        for r in rows
    ]


async def fetch_event_detail(
    session: AsyncSession, event_id: uuid.UUID
) -> EventDetail | None:
    """Full event view: the event + its sources + sub-timeline references."""
    row = (
        await session.execute(
            text(f"SELECT {_EVENT_COLS}, body FROM events WHERE id = :id"),
            {"id": event_id},
        )
    ).first()
    if row is None:
        return None

    source_rows = (
        await session.execute(
            text(
                "SELECT s.id, s.url, s.domain, s.title, s.publisher, s.published_at, "
                "s.kind, s.quality_score FROM event_sources es "
                "JOIN sources s ON s.id = es.source_id WHERE es.event_id = :id "
                "ORDER BY s.published_at NULLS LAST"
            ),
            {"id": event_id},
        )
    ).all()

    # Local import avoids a module-level cycle (graph_queries reuses helpers from here).
    from chronos_api.graph_queries import fetch_event_entities, fetch_event_media

    base = _event_read(row)
    return EventDetail(
        **base.model_dump(),
        body=row.body,
        sources=[
            SourceRead(
                id=s.id,
                url=s.url,
                domain=s.domain,
                title=s.title,
                publisher=s.publisher,
                published_at=s.published_at,
                kind=s.kind,
                quality_score=s.quality_score,
            )
            for s in source_rows
        ],
        references=await fetch_subtimeline(session, event_id),
        entities=await fetch_event_entities(session, event_id),
        media=await fetch_event_media(session, event_id),
    )
