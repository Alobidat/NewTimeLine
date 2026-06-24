"""In-app notifications (Phase 5 — the system reaches out).

Notifications are generated synchronously by the interaction routers when someone follows you
or likes / comments / replies / reposts your content. Self-actions and agent-curated content
(no recipient) are skipped. Reads power the bell badge + the notifications inbox.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.models.social import NOTIFICATION_KINDS, Notification


async def event_author_id(session: AsyncSession, event_id: uuid.UUID) -> uuid.UUID | None:
    """The user who uploaded the event's hero clip (``media.origin_kind='user'``), or None for
    agent/seed events (no personal recipient). Mirrors the feed's ``_HERO_JOIN`` author rule."""
    row = (
        await session.execute(
            text(
                "SELECT em.added_by FROM event_media em JOIN media m ON m.id = em.media_id "
                "WHERE em.event_id = :eid AND em.role = 'hero' AND m.origin_kind = 'user' "
                "ORDER BY em.rank LIMIT 1"
            ),
            {"eid": event_id},
        )
    ).first()
    if not row or not row.added_by:
        return None
    try:
        return uuid.UUID(str(row.added_by))
    except (ValueError, TypeError):
        return None


async def notify(
    session: AsyncSession,
    *,
    recipient_id: uuid.UUID | None,
    actor_id: uuid.UUID,
    kind: str,
    event_id: uuid.UUID | None = None,
) -> Notification | None:
    """Create one notification (best-effort). No-op for a null recipient, a self-action, or an
    unknown kind — so notifying never breaks the action that triggered it. Caller commits."""
    if recipient_id is None or recipient_id == actor_id or kind not in NOTIFICATION_KINDS:
        return None
    row = Notification(
        recipient_id=recipient_id, actor_id=actor_id, kind=kind, event_id=event_id
    )
    session.add(row)
    return row


async def notify_event_author(
    session: AsyncSession, *, event_id: uuid.UUID, actor_id: uuid.UUID, kind: str
) -> Notification | None:
    """Resolve an event's author and notify them (skips agent clips + self-actions)."""
    recipient = await event_author_id(session, event_id)
    return await notify(
        session, recipient_id=recipient, actor_id=actor_id, kind=kind, event_id=event_id
    )


async def list_for_user(
    session: AsyncSession, *, user_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> list[Notification]:
    """A user's notifications, newest-first."""
    rows = (
        await session.execute(
            select(Notification)
            .where(Notification.recipient_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows)


async def unread_count(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """How many unread notifications the user has (the bell badge)."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_id == user_id, Notification.read.is_(False))
        )
        or 0
    )


async def mark_read(
    session: AsyncSession, *, user_id: uuid.UUID, notification_id: uuid.UUID
) -> bool:
    """Mark one of the user's notifications read. Returns True if a row changed. Caller commits."""
    res = await session.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.recipient_id == user_id)
        .values(read=True)
    )
    return (res.rowcount or 0) > 0


async def mark_all_read(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Mark all the user's notifications read. Returns the count changed. Caller commits."""
    res = await session.execute(
        update(Notification)
        .where(Notification.recipient_id == user_id, Notification.read.is_(False))
        .values(read=True)
    )
    return res.rowcount or 0
