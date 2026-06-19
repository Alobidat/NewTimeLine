"""Event endpoints: read detail, create, the per-event sub-timeline, and the history-graph
views (tagged entities, related events, and the back-and-forth causal chain)."""

from __future__ import annotations

import uuid

from chronos_core import repository
from chronos_core.schemas.event import EventCreate, EventDetail, EventRead, EventReferenceRead
from chronos_core.schemas.graph import ChainResponse, EntityRole, RelatedEvent
from chronos_core.schemas.media import MediaRead
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session
from chronos_api.graph_queries import (
    events_for_entities,
    fetch_chain,
    fetch_event_entities,
    fetch_event_media,
    fetch_related,
)
from chronos_api.queries import fetch_event_detail, fetch_subtimeline

router = APIRouter(prefix="/events", tags=["events"])


def _parse_ids(ids: str) -> list[uuid.UUID]:
    """Parse a comma-separated list of entity UUIDs, rejecting malformed values."""
    try:
        return [uuid.UUID(part) for part in ids.split(",") if part.strip()]
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"bad entity id: {exc}") from exc


# NOTE: static paths are declared before "/{event_id}" so they are not captured as an id.


@router.get("/by-entities", response_model=list[EventRead])
async def events_by_entities(
    ids: str = Query(description="comma-separated entity UUIDs; events linked to ALL of them"),
    t0: float | None = Query(default=None, description="from year (signed)"),
    t1: float | None = Query(default=None, description="to year (signed)"),
    limit: int = Query(default=200, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[EventRead]:
    """Events linking *all* of the given entities — e.g. every event involving both the
    US and Iran — time-ordered."""
    return await events_for_entities(session, _parse_ids(ids), t0=t0, t1=t1, limit=limit)


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> EventDetail:
    """Full event view: sources, sub-timeline references, tagged entities, and media."""
    detail = await fetch_event_detail(session, event_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return detail


@router.get("/{event_id}/subtimeline", response_model=list[EventReferenceRead])
async def get_subtimeline(
    event_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[EventReferenceRead]:
    """The deep-time subjects this event discusses (the sub-timeline)."""
    return await fetch_subtimeline(session, event_id)


@router.get("/{event_id}/entities", response_model=list[EntityRole])
async def get_event_entities(
    event_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[EntityRole]:
    """The entities (people/orgs/places/topics) tagged on this event, with their roles."""
    return await fetch_event_entities(session, event_id)


@router.get("/{event_id}/media", response_model=list[MediaRead])
async def get_event_media(
    event_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[MediaRead]:
    """Images / video clips attached to this event."""
    return await fetch_event_media(session, event_id)


@router.get("/{event_id}/related", response_model=list[RelatedEvent])
async def get_related(
    event_id: uuid.UUID,
    direction: str = Query(default="both", pattern="^(back|forward|both)$"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[RelatedEvent]:
    """One-hop neighbors across all relation kinds (same-place, same-actor, causal …)."""
    return await fetch_related(session, event_id, direction=direction, limit=limit)


@router.get("/{event_id}/chain", response_model=ChainResponse)
async def get_chain(
    event_id: uuid.UUID,
    direction: str = Query(default="both", pattern="^(back|forward|both)$"),
    depth: int = Query(default=2, ge=1, le=4),
    session: AsyncSession = Depends(get_session),
) -> ChainResponse:
    """The causal chain: follow ``back`` (what led to this) / ``forward`` (what it caused)
    relations to ``depth`` hops — the dig back-and-forth through history."""
    return await fetch_chain(session, event_id, direction=direction, depth=depth)


@router.post("", response_model=EventDetail, status_code=status.HTTP_201_CREATED)
async def create_event(
    data: EventCreate, session: AsyncSession = Depends(get_session)
) -> EventDetail:
    """Create an event (manual/admin use; agents use the shared repository directly)."""
    event = await repository.create_event(session, data)
    await session.flush()
    detail = await fetch_event_detail(session, event.id)
    assert detail is not None  # just created
    return detail
