"""User-created event links (ADR-0025 §2.4): a user asserts a relation between two events.

These are ``event_relations`` rows with ``created_by`` = the actor's user id (so the
related-events view tags them "added by a user" vs agent-derived edges — see
``RelatedEvent.origin``). ``kind`` defaults to ``thematic``, the non-causal default for a
user link. Writes require ``require_verified_actor`` (signed-in, email-verified, agreement
accepted — ADR-0026).
"""

from __future__ import annotations

import uuid

from chronos_core import interactions_repo as repo
from chronos_core.schemas.interaction import EventLinkCreate, EventLinkResult
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.auth_stub import require_verified_actor
from chronos_api.deps import get_session

router = APIRouter(prefix="/links", tags=["links"])


@router.post("", response_model=EventLinkResult, status_code=status.HTTP_201_CREATED)
async def create_link(
    data: EventLinkCreate,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> EventLinkResult:
    """Add a directed src→dst relation between two events, attributed to the caller."""
    try:
        created = await repo.add_user_link(
            session,
            src_event=data.src_event,
            dst_event=data.dst_event,
            kind=data.kind,
            user_id=actor,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return EventLinkResult(
        src_event=data.src_event, dst_event=data.dst_event, kind=data.kind, created=created
    )


@router.delete("", response_model=EventLinkResult)
async def remove_link(
    src_event: uuid.UUID = Query(),
    dst_event: uuid.UUID = Query(),
    kind: str = Query(default="thematic"),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> EventLinkResult:
    """Remove your own event-link. Only edges you created (``created_by`` = your id) are
    removed — agent-derived edges are left untouched."""
    removed = await repo.remove_user_link(
        session, src_event=src_event, dst_event=dst_event, kind=kind, user_id=actor
    )
    return EventLinkResult(
        src_event=src_event, dst_event=dst_event, kind=kind, removed=removed
    )
