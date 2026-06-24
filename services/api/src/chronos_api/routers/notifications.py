"""In-app notifications inbox (Phase 5 — the system reaches out).

The bell/notifications list for the signed-in user: who followed them or liked / commented /
replied / reposted their content. Notifications are *generated* synchronously by the interaction
routers (see ``notifications_repo.notify*``); this router only reads + marks-read.
"""

from __future__ import annotations

import uuid

from chronos_core import notifications_repo as repo
from chronos_core import social_repo
from chronos_core.schemas.interaction import CommentAuthor
from chronos_core.schemas.social import NotificationList, NotificationRead
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.auth_stub import require_verified_actor
from chronos_api.deps import get_session

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> NotificationList:
    """The caller's notifications (newest-first) + the unread badge count."""
    rows = await repo.list_for_user(session, user_id=actor, limit=limit, offset=offset)
    unread = await repo.unread_count(session, user_id=actor)

    users = await social_repo.users_by_ids(session, list({n.actor_id for n in rows}))
    event_ids = [n.event_id for n in rows if n.event_id is not None]
    titles: dict[uuid.UUID, str] = {}
    if event_ids:
        titles = {
            r.id: r.title
            for r in (
                await session.execute(
                    text("SELECT id, title FROM events WHERE id = ANY(:ids)"),
                    {"ids": event_ids},
                )
            ).all()
        }

    items = [
        NotificationRead(
            id=n.id,
            kind=n.kind,
            actor=(
                CommentAuthor(
                    id=u.id, handle=u.handle,
                    display_name=u.display_name, avatar_url=u.avatar_url,
                )
                if (u := users.get(n.actor_id)) is not None
                else None
            ),
            event_id=n.event_id,
            event_title=titles.get(n.event_id) if n.event_id else None,
            read=n.read,
            created_at=n.created_at,
        )
        for n in rows
    ]
    return NotificationList(items=items, unread=unread)


@router.post("/read")
async def mark_all_read(
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> dict[str, int]:
    """Mark all the caller's notifications read (clears the badge)."""
    return {"marked": await repo.mark_all_read(session, user_id=actor)}


@router.post("/{notification_id}/read")
async def mark_one_read(
    notification_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> dict[str, bool]:
    """Mark a single notification read."""
    return {"read": await repo.mark_read(session, user_id=actor, notification_id=notification_id)}
