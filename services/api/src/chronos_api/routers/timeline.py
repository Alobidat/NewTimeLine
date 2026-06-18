"""Timeline + map endpoints — the data behind the magical timeline.

Times are signed years (ADR-0012): pass ``t0``/``t1`` like ``-4000000`` … ``2026.5``.
"""

from __future__ import annotations

from chronos_core.schemas.event import EventRead
from chronos_core.schemas.timeline import TimelineResponse
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session
from chronos_api.queries import TimelineParams, fetch_map, fetch_timeline

router = APIRouter(tags=["timeline"])

_BBOX = "minLon,minLat,maxLon,maxLat"


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    """Parse a 'minLon,minLat,maxLon,maxLat' string into a tuple (or None)."""
    if not bbox:
        return None
    try:
        parts = tuple(float(x) for x in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"bad bbox; expected {_BBOX}") from exc
    if len(parts) != 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"bad bbox; expected {_BBOX}")
    return parts  # type: ignore[return-value]


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    t0: float = Query(..., description="window start (signed year)"),
    t1: float = Query(..., description="window end (signed year)"),
    bbox: str | None = Query(None, description=_BBOX),
    category: str | None = None,
    min_severity: int = Query(0, ge=0, le=100),
    max_events: int = Query(500, ge=1, le=2000),
    buckets: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    """Events when the window is sparse; aggregated buckets when dense (the heatline)."""
    params = TimelineParams(
        t0=t0,
        t1=t1,
        bbox=_parse_bbox(bbox),
        category=category,
        min_severity=min_severity,
        max_events=max_events,
        buckets=buckets,
    )
    return await fetch_timeline(session, params)


@router.get("/map", response_model=list[EventRead])
async def get_map(
    bbox: str = Query(..., description=_BBOX),
    t0: float = Query(-5_000_000_000, description="window start (signed year)"),
    t1: float = Query(10_000, description="window end (signed year)"),
    min_severity: int = Query(0, ge=0, le=100),
    limit: int = Query(1000, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
) -> list[EventRead]:
    """Geolocated events within a viewport bbox + (optional) time window."""
    parsed = _parse_bbox(bbox)
    assert parsed is not None  # bbox is required here
    return await fetch_map(session, parsed, t0, t1, min_severity, limit)
