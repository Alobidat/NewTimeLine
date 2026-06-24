"""Write/read helpers for the interaction substrate (ADR-0025).

Pure DB logic shared by the API routers (and reusable by future workers): create/edit/delete
comments, toggle reactions, cast source votes, and add/remove user event-links. The actor is
always passed in by the caller (resolved by the ``get_actor`` identity stub) — these helpers
never invent an identity. Callers commit.

Kept separate from :mod:`chronos_core.repository` (event/source writes) so each file stays
small and single-responsibility (engineering-standards.md).
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.models.interaction import (
    COMMENT_STATUSES,
    REACTION_KINDS,
    VOTE_VERDICTS,
    Comment,
    CommentReaction,
    Reaction,
    SourceVote,
)
from chronos_core.models.relation import EventRelation
from chronos_core.models.user import User

# --- validation helpers ---------------------------------------------------------------


def is_reaction_kind(kind: str) -> bool:
    return kind in REACTION_KINDS


def is_vote_verdict(verdict: str) -> bool:
    return verdict in VOTE_VERDICTS


# --- comments -------------------------------------------------------------------------


async def list_comments(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    limit: int = 100,
    offset: int = 0,
    include_removed: bool = False,
) -> list[Comment]:
    """All comments on an event, oldest-first (so a client can assemble the thread tree
    from ``parent_id``). Removed comments are hidden unless ``include_removed``."""
    stmt = select(Comment).where(Comment.event_id == event_id)
    if not include_removed:
        stmt = stmt.where(Comment.status != "removed")
    stmt = stmt.order_by(Comment.created_at).limit(limit).offset(offset)
    return list((await session.scalars(stmt)).all())


async def get_comment(session: AsyncSession, comment_id: uuid.UUID) -> Comment | None:
    """Fetch one comment by id (used to resolve a reply's parent author for notifications)."""
    return await session.get(Comment, comment_id)


async def create_comment(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    body: str,
    parent_id: uuid.UUID | None = None,
) -> Comment:
    """Insert a comment (or a reply). If ``parent_id`` is given it must belong to the same
    event — raises ``ValueError`` otherwise. Caller commits."""
    if parent_id is not None:
        parent = await session.get(Comment, parent_id)
        if parent is None or parent.event_id != event_id:
            raise ValueError("parent comment not found on this event")
    comment = Comment(
        event_id=event_id, user_id=user_id, parent_id=parent_id, body=body,
        status="visible",
    )
    session.add(comment)
    await session.flush()
    return comment


async def edit_comment(
    session: AsyncSession, comment_id: uuid.UUID, *, user_id: uuid.UUID, body: str
) -> Comment | None:
    """Edit a comment's body. Returns the comment, or ``None`` if it doesn't exist.
    Raises ``PermissionError`` if the actor isn't the author."""
    comment = await session.get(Comment, comment_id)
    if comment is None:
        return None
    if comment.user_id != user_id:
        raise PermissionError("not the comment author")
    comment.body = body
    return comment


async def soft_delete_comment(
    session: AsyncSession, comment_id: uuid.UUID, *, user_id: uuid.UUID
) -> Comment | None:
    """Soft-delete (``status='removed'``) a comment. Returns it, or ``None`` if absent.
    Raises ``PermissionError`` if the actor isn't the author. The row is kept so replies
    stay attached and moderation history is preserved."""
    comment = await session.get(Comment, comment_id)
    if comment is None:
        return None
    if comment.user_id != user_id:
        raise PermissionError("not the comment author")
    comment.status = "removed"
    return comment


async def set_comment_status(
    session: AsyncSession, comment_id: uuid.UUID, *, status: str
) -> Comment | None:
    """Moderation: set a comment's status (visible|flagged|removed). Returns it or None."""
    if status not in COMMENT_STATUSES:
        raise ValueError(f"invalid status: {status}")
    comment = await session.get(Comment, comment_id)
    if comment is None:
        return None
    comment.status = status
    return comment


# --- reactions ------------------------------------------------------------------------


async def toggle_reaction(
    session: AsyncSession, *, event_id: uuid.UUID, user_id: uuid.UUID, kind: str
) -> bool:
    """Toggle one reaction kind for (user, event). Returns the new active state: ``True``
    if the reaction was just added, ``False`` if it was removed. Caller commits."""
    if not is_reaction_kind(kind):
        raise ValueError(f"invalid reaction kind: {kind}")
    existing = await session.get(Reaction, (user_id, event_id, kind))
    if existing is not None:
        await session.delete(existing)
        return False
    session.add(Reaction(user_id=user_id, event_id=event_id, kind=kind))
    return True


async def reaction_counts(
    session: AsyncSession, event_id: uuid.UUID
) -> dict[str, int]:
    """Count reactions per kind on an event (kinds with zero reactions are omitted)."""
    rows = (
        await session.execute(
            select(Reaction.kind, func.count())
            .where(Reaction.event_id == event_id)
            .group_by(Reaction.kind)
        )
    ).all()
    return {kind: count for kind, count in rows}


async def reactions_of(
    session: AsyncSession, event_id: uuid.UUID, user_id: uuid.UUID
) -> list[str]:
    """The reaction kinds a given actor has set on an event."""
    rows = (
        await session.scalars(
            select(Reaction.kind).where(
                Reaction.event_id == event_id, Reaction.user_id == user_id
            )
        )
    ).all()
    return list(rows)


# --- comment reactions + author enrichment --------------------------------------------


async def toggle_comment_reaction(
    session: AsyncSession, *, comment_id: uuid.UUID, user_id: uuid.UUID, kind: str
) -> bool:
    """Toggle one reaction kind for (user, comment). Returns the new active state. Same kind
    vocabulary as event reactions. Caller commits."""
    if not is_reaction_kind(kind):
        raise ValueError(f"invalid reaction kind: {kind}")
    if await session.get(Comment, comment_id) is None:
        raise ValueError("comment not found")
    existing = await session.get(CommentReaction, (user_id, comment_id, kind))
    if existing is not None:
        await session.delete(existing)
        return False
    session.add(CommentReaction(user_id=user_id, comment_id=comment_id, kind=kind))
    return True


async def comment_reaction_counts(
    session: AsyncSession, comment_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    """Per-comment reaction counts for a set of comments: ``{comment_id: {kind: n}}``."""
    if not comment_ids:
        return {}
    rows = (
        await session.execute(
            select(CommentReaction.comment_id, CommentReaction.kind, func.count())
            .where(CommentReaction.comment_id.in_(comment_ids))
            .group_by(CommentReaction.comment_id, CommentReaction.kind)
        )
    ).all()
    out: dict[uuid.UUID, dict[str, int]] = {}
    for cid, kind, count in rows:
        out.setdefault(cid, {})[kind] = count
    return out


async def comment_reactions_of(
    session: AsyncSession, comment_ids: list[uuid.UUID], user_id: uuid.UUID
) -> dict[uuid.UUID, list[str]]:
    """The kinds the caller set on each of a set of comments: ``{comment_id: [kind, ...]}``."""
    if not comment_ids:
        return {}
    rows = (
        await session.execute(
            select(CommentReaction.comment_id, CommentReaction.kind).where(
                CommentReaction.comment_id.in_(comment_ids),
                CommentReaction.user_id == user_id,
            )
        )
    ).all()
    out: dict[uuid.UUID, list[str]] = {}
    for cid, kind in rows:
        out.setdefault(cid, []).append(kind)
    return out


async def comment_count(session: AsyncSession, event_id: uuid.UUID) -> int:
    """Number of visible comments on an event (cheap COUNT — for the feed stat rail)."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Comment)
            .where(Comment.event_id == event_id, Comment.status != "removed")
        )
        or 0
    )


async def comment_authors(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, User]:
    """Batch-fetch the author ``User`` rows for a set of comment user_ids (for avatar + name)."""
    if not user_ids:
        return {}
    rows = (
        await session.scalars(select(User).where(User.id.in_(set(user_ids))))
    ).all()
    return {u.id: u for u in rows}


# --- source votes ---------------------------------------------------------------------


async def cast_source_vote(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    verdict: str,
    weight: float = 1.0,
) -> SourceVote:
    """Cast or change a vote on a source's relevance to an event (upsert on the triple).
    Caller commits."""
    if not is_vote_verdict(verdict):
        raise ValueError(f"invalid verdict: {verdict}")
    existing = await session.get(SourceVote, (user_id, event_id, source_id))
    if existing is not None:
        existing.verdict = verdict
        existing.weight = weight
        return existing
    vote = SourceVote(
        user_id=user_id,
        event_id=event_id,
        source_id=source_id,
        verdict=verdict,
        weight=weight,
    )
    session.add(vote)
    await session.flush()
    return vote


async def source_vote_tallies(
    session: AsyncSession, event_id: uuid.UUID
) -> dict[str, dict[str, int]]:
    """Per-source verdict counts for an event: ``{source_id: {verdict: count}}``."""
    rows = (
        await session.execute(
            select(SourceVote.source_id, SourceVote.verdict, func.count())
            .where(SourceVote.event_id == event_id)
            .group_by(SourceVote.source_id, SourceVote.verdict)
        )
    ).all()
    out: dict[str, dict[str, int]] = {}
    for source_id, verdict, count in rows:
        out.setdefault(str(source_id), {})[verdict] = count
    return out


async def source_votes_of(
    session: AsyncSession, event_id: uuid.UUID, user_id: uuid.UUID
) -> dict[str, str]:
    """The actor's own verdicts on an event: ``{source_id: verdict}``."""
    rows = (
        await session.execute(
            select(SourceVote.source_id, SourceVote.verdict).where(
                SourceVote.event_id == event_id, SourceVote.user_id == user_id
            )
        )
    ).all()
    return {str(source_id): verdict for source_id, verdict in rows}


# --- user event links -----------------------------------------------------------------


async def add_user_link(
    session: AsyncSession,
    *,
    src_event: uuid.UUID,
    dst_event: uuid.UUID,
    kind: str,
    user_id: uuid.UUID,
    weight: float = 1.0,
) -> bool:
    """Create a user-asserted directed edge between two events (idempotent per kind).

    Records ``created_by`` = the actor's id (string) so the related-events view can tag the
    edge "added by a user" vs an agent run. Returns ``True`` if a new edge was inserted.
    Rejects self-loops. Caller commits."""
    if src_event == dst_event:
        raise ValueError("cannot link an event to itself")
    existing = await session.get(EventRelation, (src_event, dst_event, kind))
    if existing is not None:
        return False
    session.add(
        EventRelation(
            src_event=src_event,
            dst_event=dst_event,
            kind=kind,
            weight=weight,
            created_by=str(user_id),
        )
    )
    return True


async def remove_user_link(
    session: AsyncSession,
    *,
    src_event: uuid.UUID,
    dst_event: uuid.UUID,
    kind: str,
    user_id: uuid.UUID,
) -> bool:
    """Remove a user's own event-link. Only deletes an edge whose ``created_by`` matches the
    actor (so a user can't delete an agent-derived edge). Returns ``True`` if a row was
    deleted. Caller commits."""
    result = await session.execute(
        delete(EventRelation).where(
            EventRelation.src_event == src_event,
            EventRelation.dst_event == dst_event,
            EventRelation.kind == kind,
            EventRelation.created_by == str(user_id),
        )
    )
    return (result.rowcount or 0) > 0
