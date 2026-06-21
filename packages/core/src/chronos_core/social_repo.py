"""Write/read helpers for the social graph + promotes + activity log (Phase 4-B).

Pure DB logic shared by the API routers (and reusable by workers): follow/unfollow, promote/
demote, follower/following lists + counts, and recording activity. The actor is always passed
in by the caller (resolved by the auth seam) — these helpers never invent an identity. Callers
commit.

Kept separate from :mod:`chronos_core.interactions_repo` (event comments/reactions/source
votes) so each file stays small and single-responsibility (engineering-standards.md).
"""

from __future__ import annotations

import uuid

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.models.social import (
    ACTIVITY_KINDS,
    ACTIVITY_TARGETS,
    FOLLOW_TARGETS,
    PROMOTE_TARGETS,
    ActivityLog,
    Follow,
    Promote,
)

# --- validation helpers ---------------------------------------------------------------


def is_follow_target(t: str) -> bool:
    return t in FOLLOW_TARGETS


def is_promote_target(t: str) -> bool:
    return t in PROMOTE_TARGETS


# --- follows --------------------------------------------------------------------------


async def follow(
    session: AsyncSession, *, user_id: uuid.UUID, target_type: str, target_id: uuid.UUID
) -> bool:
    """Follow a user|entity|event (idempotent). Returns True if a new edge was created.
    Rejects a user following themselves. Caller commits."""
    if not is_follow_target(target_type):
        raise ValueError(f"invalid follow target: {target_type}")
    if target_type == "user" and target_id == user_id:
        raise ValueError("cannot follow yourself")
    existing = await session.get(Follow, (user_id, target_type, target_id))
    if existing is not None:
        return False
    session.add(Follow(user_id=user_id, target_type=target_type, target_id=target_id))
    return True


async def unfollow(
    session: AsyncSession, *, user_id: uuid.UUID, target_type: str, target_id: uuid.UUID
) -> bool:
    """Remove a follow edge. Returns True if a row was deleted. Caller commits."""
    result = await session.execute(
        delete(Follow).where(
            Follow.user_id == user_id,
            Follow.target_type == target_type,
            Follow.target_id == target_id,
        )
    )
    return (result.rowcount or 0) > 0


async def is_following(
    session: AsyncSession, *, user_id: uuid.UUID, target_type: str, target_id: uuid.UUID
) -> bool:
    """True iff the caller follows the given target."""
    return (await session.get(Follow, (user_id, target_type, target_id))) is not None


async def followers(
    session: AsyncSession, *, target_type: str, target_id: uuid.UUID, limit: int = 100, offset: int = 0
) -> list[uuid.UUID]:
    """User ids that follow a target, most-recent-first."""
    rows = (
        await session.scalars(
            select(Follow.user_id)
            .where(Follow.target_type == target_type, Follow.target_id == target_id)
            .order_by(Follow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows)


async def following(
    session: AsyncSession, *, user_id: uuid.UUID, target_type: str | None = None,
    limit: int = 100, offset: int = 0,
) -> list[tuple[str, uuid.UUID]]:
    """(target_type, target_id) edges the user follows, most-recent-first. Optionally
    filtered to a single ``target_type``."""
    stmt = select(Follow.target_type, Follow.target_id).where(Follow.user_id == user_id)
    if target_type is not None:
        stmt = stmt.where(Follow.target_type == target_type)
    stmt = stmt.order_by(Follow.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).all()
    return [(t, i) for t, i in rows]


async def follower_count(
    session: AsyncSession, *, target_type: str, target_id: uuid.UUID
) -> int:
    """How many users follow a target."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Follow)
            .where(Follow.target_type == target_type, Follow.target_id == target_id)
        )
        or 0
    )


async def following_count(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """How many targets a user follows (all kinds)."""
    return int(
        await session.scalar(
            select(func.count()).select_from(Follow).where(Follow.user_id == user_id)
        )
        or 0
    )


# --- promotes -------------------------------------------------------------------------


async def cast_promote(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    value: int,
) -> int:
    """Promote (+1) / demote (-1) / clear (0) a graph object (upsert on the triple).

    Returns the caller's stored value (0 if cleared). Caller commits."""
    if not is_promote_target(target_type):
        raise ValueError(f"invalid promote target: {target_type}")
    if value not in (-1, 0, 1):
        raise ValueError("promote value must be -1, 0, or +1")
    existing = await session.get(Promote, (user_id, target_type, target_id))
    if value == 0:
        if existing is not None:
            await session.delete(existing)
        return 0
    if existing is not None:
        existing.value = value
        return value
    session.add(
        Promote(user_id=user_id, target_type=target_type, target_id=target_id, value=value)
    )
    return value


async def promote_tally(
    session: AsyncSession, *, target_type: str, target_id: uuid.UUID
) -> tuple[int, int, int]:
    """Aggregate (score, up, down) for a target. ``score`` = up − down."""
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(Promote.value), 0),
                func.coalesce(func.sum(case((Promote.value > 0, 1), else_=0)), 0),
                func.coalesce(func.sum(case((Promote.value < 0, 1), else_=0)), 0),
            ).where(Promote.target_type == target_type, Promote.target_id == target_id)
        )
    ).first()
    if row is None:
        return 0, 0, 0
    return int(row[0]), int(row[1]), int(row[2])


async def my_promote(
    session: AsyncSession, *, user_id: uuid.UUID, target_type: str, target_id: uuid.UUID
) -> int:
    """The caller's current promote value on a target (0 if none)."""
    existing = await session.get(Promote, (user_id, target_type, target_id))
    return int(existing.value) if existing is not None else 0


# --- activity log ---------------------------------------------------------------------


async def record_activity(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    kind: str,
    target_type: str,
    target_id: uuid.UUID,
    weight: float | None = None,
) -> ActivityLog | None:
    """Append one activity row (the interest-profile substrate, ADR-0028).

    Best-effort by design: an unknown ``kind``/``target_type`` is ignored (returns ``None``)
    so logging never breaks the action that triggered it. ``weight`` defaults to a per-kind
    value (a promote/comment is worth more than a passing view). Caller commits."""
    if kind not in ACTIVITY_KINDS or target_type not in ACTIVITY_TARGETS:
        return None
    row = ActivityLog(
        user_id=user_id,
        kind=kind,
        target_type=target_type,
        target_id=target_id,
        weight=default_weight(kind) if weight is None else weight,
    )
    session.add(row)
    return row


# Per-kind base weights for the interest profile (deeper engagement → higher weight).
_KIND_WEIGHT = {
    "view": 0.5, "dwell": 1.0, "watch": 1.5, "like": 2.0, "share": 2.5,
    "comment": 3.0, "promote": 3.0, "follow": 4.0, "upload": 5.0,
}


def default_weight(kind: str) -> float:
    """The default activity weight for a kind."""
    return _KIND_WEIGHT.get(kind, 1.0)
