"""Moderation-flag read/write helpers (the admin approvals queue).

A flag is raised (LLM or user), held content waits in ``pending``/``flagged`` until an admin
``approve``s (clears the flag + un-holds) or ``remove``s the content. Callers commit.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.models.interaction import Comment
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.models.moderation import ModerationFlag


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def raise_flag(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    reason: str | None,
    severity: int,
    source: str = "llm",
) -> ModerationFlag:
    """Insert an ``open`` flag (no dedup — repeated flags are fine, the queue groups by target)."""
    flag = ModerationFlag(
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        severity=severity,
        source=source,
        status="open",
    )
    session.add(flag)
    await session.flush()
    return flag


async def open_count(session: AsyncSession) -> int:
    """How many flags are awaiting review (the admin badge)."""
    return int(
        await session.scalar(
            select(func.count()).select_from(ModerationFlag).where(ModerationFlag.status == "open")
        )
        or 0
    )


async def list_open(
    session: AsyncSession, *, limit: int = 100, offset: int = 0
) -> list[ModerationFlag]:
    """Open flags, most-recent-first (highest severity first within a timestamp tie)."""
    return list(
        (
            await session.scalars(
                select(ModerationFlag)
                .where(ModerationFlag.status == "open")
                .order_by(ModerationFlag.created_at.desc(), ModerationFlag.severity.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )


async def approve(
    session: AsyncSession, *, flag_id: uuid.UUID, admin_id: uuid.UUID | None
) -> ModerationFlag | None:
    """Clear a flag and un-hold its target (event pending→published, comment flagged→visible)."""
    flag = await session.get(ModerationFlag, flag_id)
    if flag is None:
        return None
    flag.status = "approved"
    flag.resolved_at = _now()
    flag.resolved_by = admin_id
    if flag.target_type == "event":
        event = await session.get(Event, flag.target_id)
        if event is not None and event.status == EventStatus.PENDING:
            event.status = EventStatus.PUBLISHED
    elif flag.target_type == "comment":
        comment = await session.get(Comment, flag.target_id)
        if comment is not None and comment.status == "flagged":
            comment.status = "visible"
    return flag


async def remove(
    session: AsyncSession, *, flag_id: uuid.UUID, admin_id: uuid.UUID | None
) -> ModerationFlag | None:
    """Retract the flagged content: event→retracted, comment→removed; resolve the flag."""
    flag = await session.get(ModerationFlag, flag_id)
    if flag is None:
        return None
    flag.status = "removed"
    flag.resolved_at = _now()
    flag.resolved_by = admin_id
    if flag.target_type == "event":
        event = await session.get(Event, flag.target_id)
        if event is not None:
            event.status = EventStatus.RETRACTED
    elif flag.target_type == "comment":
        comment = await session.get(Comment, flag.target_id)
        if comment is not None:
            comment.status = "removed"
    return flag
