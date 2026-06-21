"""Interaction endpoints for an event: threaded comments, reactions, and source votes
(ADR-0025). All writes resolve their actor through the ``get_actor`` identity stub; reads
also report the caller's own set/verdicts so the UI can render toggle state.

User-created event *links* live in :mod:`chronos_api.routers.links` (they relate two events,
not one). Everything here is nested under ``/events/{event_id}``.
"""

from __future__ import annotations

import uuid

from chronos_core import interactions_repo as repo
from chronos_core.schemas.interaction import (
    CommentCreate,
    CommentRead,
    CommentUpdate,
    ReactionSummary,
    ReactionToggle,
    ReactionToggleResult,
    SourceVoteCast,
    SourceVoteResult,
    SourceVoteSummary,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.auth_stub import get_actor, require_verified_actor
from chronos_api.deps import get_session

router = APIRouter(prefix="/events/{event_id}", tags=["interactions"])


# --- comments -------------------------------------------------------------------------


@router.get("/comments", response_model=list[CommentRead])
async def list_comments(
    event_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[CommentRead]:
    """Comments on an event, oldest-first + paged. ``parent_id`` lets the client assemble
    the reply tree; removed comments are omitted."""
    rows = await repo.list_comments(session, event_id, limit=limit, offset=offset)
    return [CommentRead.model_validate(c, from_attributes=True) for c in rows]


@router.post("/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    event_id: uuid.UUID,
    data: CommentCreate,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> CommentRead:
    """Post a comment, or a reply when ``parent_id`` is set."""
    try:
        comment = await repo.create_comment(
            session, event_id=event_id, user_id=actor, body=data.body, parent_id=data.parent_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return CommentRead.model_validate(comment, from_attributes=True)


@router.patch("/comments/{comment_id}", response_model=CommentRead)
async def edit_comment(
    event_id: uuid.UUID,
    comment_id: uuid.UUID,
    data: CommentUpdate,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> CommentRead:
    """Edit the body of your own comment."""
    try:
        comment = await repo.edit_comment(session, comment_id, user_id=actor, body=data.body)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "comment not found")
    return CommentRead.model_validate(comment, from_attributes=True)


@router.delete("/comments/{comment_id}", response_model=CommentRead)
async def delete_comment(
    event_id: uuid.UUID,
    comment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> CommentRead:
    """Soft-delete your own comment (status → removed; the row is kept for thread integrity)."""
    try:
        comment = await repo.soft_delete_comment(session, comment_id, user_id=actor)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "comment not found")
    return CommentRead.model_validate(comment, from_attributes=True)


# --- reactions ------------------------------------------------------------------------


@router.get("/reactions", response_model=ReactionSummary)
async def get_reactions(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> ReactionSummary:
    """Aggregate reaction counts for an event + the caller's own set."""
    counts = await repo.reaction_counts(session, event_id)
    mine = await repo.reactions_of(session, event_id, actor)
    return ReactionSummary(event_id=event_id, counts=counts, mine=mine)


@router.post("/reactions", response_model=ReactionToggleResult)
async def toggle_reaction(
    event_id: uuid.UUID,
    data: ReactionToggle,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> ReactionToggleResult:
    """Toggle a reaction kind on/off for the caller, returning the fresh aggregate."""
    try:
        active = await repo.toggle_reaction(
            session, event_id=event_id, user_id=actor, kind=data.kind
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await session.flush()
    counts = await repo.reaction_counts(session, event_id)
    mine = await repo.reactions_of(session, event_id, actor)
    return ReactionToggleResult(kind=data.kind, active=active, counts=counts, mine=mine)


# --- source votes ---------------------------------------------------------------------


@router.get("/source-votes", response_model=SourceVoteSummary)
async def get_source_votes(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> SourceVoteSummary:
    """Per-source verdict tallies for an event + the caller's own verdicts."""
    tallies = await repo.source_vote_tallies(session, event_id)
    mine = await repo.source_votes_of(session, event_id, actor)
    return SourceVoteSummary(event_id=event_id, tallies=tallies, mine=mine)


@router.post("/source-votes", response_model=SourceVoteResult)
async def cast_source_vote(
    event_id: uuid.UUID,
    data: SourceVoteCast,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> SourceVoteResult:
    """Cast or change your verdict on a source's relevance to this event."""
    try:
        await repo.cast_source_vote(
            session,
            event_id=event_id,
            source_id=data.source_id,
            user_id=actor,
            verdict=data.verdict,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await session.flush()
    tallies = await repo.source_vote_tallies(session, event_id)
    return SourceVoteResult(source_id=data.source_id, verdict=data.verdict, tallies=tallies)
