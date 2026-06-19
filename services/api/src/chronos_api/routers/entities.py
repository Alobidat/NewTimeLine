"""Entity endpoints — search the people/orgs/places/topics that anchor the history graph,
and list a single entity's events along the timeline."""

from __future__ import annotations

import uuid

from chronos_core.schemas.event import EventRead
from chronos_core.schemas.graph import EntityRead
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session
from chronos_api.graph_queries import events_for_entities, search_entities

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("", response_model=list[EntityRead])
async def list_entities(
    q: str | None = Query(default=None, description="name substring"),
    kind: str | None = Query(default=None, description="person | org | place | topic"),
    limit: int = Query(default=30, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[EntityRead]:
    """Find entities by name, busiest (most events) first."""
    return await search_entities(session, q=q, kind=kind, limit=limit)


@router.get("/{entity_id}/events", response_model=list[EventRead])
async def entity_events(
    entity_id: uuid.UUID,
    t0: float | None = Query(default=None, description="from year (signed)"),
    t1: float | None = Query(default=None, description="to year (signed)"),
    limit: int = Query(default=200, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[EventRead]:
    """All events tagged with this entity, time-ordered."""
    return await events_for_entities(session, [entity_id], t0=t0, t1=t1, limit=limit)
