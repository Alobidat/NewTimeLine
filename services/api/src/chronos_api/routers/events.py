"""Event endpoints: read detail, create, and the per-event sub-timeline."""

from __future__ import annotations

import uuid

from chronos_core import repository
from chronos_core.schemas.event import EventCreate, EventDetail, EventReferenceRead
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session
from chronos_api.queries import fetch_event_detail, fetch_subtimeline

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> EventDetail:
    """Full event view: sources + sub-timeline references."""
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
