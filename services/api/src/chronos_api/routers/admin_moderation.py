"""Admin moderation queue (Phase 6) — review + resolve flags raised by the LLM pass.

- GET  /admin/moderation        — open flags (newest first) with a content preview.
- GET  /admin/moderation/count  — number of open flags (the overview badge).
- POST /admin/moderation/{id}/approve  — clear the flag + un-hold the content.
- POST /admin/moderation/{id}/remove   — retract the content (event→retracted, comment→removed).

All gated by ``require_admin``.
"""

from __future__ import annotations

import uuid

from chronos_core import moderation_repo
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.models.interaction import Comment
from chronos_core.schemas.moderation import ModerationFlagRead, ModerationQueue
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session, require_admin

router = APIRouter(
    prefix="/admin/moderation", tags=["admin"], dependencies=[Depends(require_admin)]
)


async def _read(session: AsyncSession, flag) -> ModerationFlagRead:
    preview, held = None, False
    if flag.target_type == "event":
        ev = await session.get(Event, flag.target_id)
        if ev is not None:
            preview = ev.title
            held = ev.status == EventStatus.PENDING
    elif flag.target_type == "comment":
        c = await session.get(Comment, flag.target_id)
        if c is not None:
            preview = c.body[:200]
            held = c.status == "flagged"
    return ModerationFlagRead(
        id=flag.id, target_type=flag.target_type, target_id=flag.target_id,
        source=flag.source, reason=flag.reason, severity=flag.severity, status=flag.status,
        created_at=flag.created_at, preview=preview, held=held,
    )


@router.get("", response_model=ModerationQueue)
async def queue(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ModerationQueue:
    flags = await moderation_repo.list_open(session, limit=limit, offset=offset)
    items = [await _read(session, f) for f in flags]
    return ModerationQueue(items=items, count=await moderation_repo.open_count(session))


@router.get("/count")
async def count(session: AsyncSession = Depends(get_session)) -> dict:
    return {"open": await moderation_repo.open_count(session)}


@router.post("/{flag_id}/approve", response_model=ModerationFlagRead)
async def approve(
    flag_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    admin: str = Depends(require_admin),
) -> ModerationFlagRead:
    flag = await moderation_repo.approve(session, flag_id=flag_id, admin_id=None)
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flag not found")
    await session.flush()
    return await _read(session, flag)


@router.post("/{flag_id}/remove", response_model=ModerationFlagRead)
async def remove(
    flag_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    admin: str = Depends(require_admin),
) -> ModerationFlagRead:
    flag = await moderation_repo.remove(session, flag_id=flag_id, admin_id=None)
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flag not found")
    await session.flush()
    return await _read(session, flag)
