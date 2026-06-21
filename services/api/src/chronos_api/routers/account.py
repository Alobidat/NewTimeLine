"""Account + GDPR self-service endpoints (ADR-0026).

- GET    /account/me      — the caller's own account (requires a session, not the gate).
- GET    /account/export  — a portable JSON archive of everything we hold (GDPR download).
- DELETE /account         — irreversibly purge the user + ALL their data (GDPR delete).

``me``/``export``/``delete`` require a *signed-in* caller (a valid session JWT) but NOT the
full write gate — a user must always be able to read and delete their own data even if they
never accepted the agreement or verified their email. We enforce sign-in by rejecting the
anonymous fallback id.
"""

from __future__ import annotations

import uuid

from chronos_core import accounts_repo, objectstore
from chronos_core.models.user import User
from chronos_core.schemas.auth import PurgeResult, UserMe
from chronos_core.schemas.event import EventRead
from chronos_core.settings import get_settings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.auth_stub import get_actor
from chronos_api.deps import get_session
from chronos_api.queries import _EVENT_COLS, _event_read

router = APIRouter(prefix="/account", tags=["account"])


def _require_signed_in(actor: uuid.UUID) -> uuid.UUID:
    """Reject the dev/anonymous fallback id — these endpoints need a real session."""
    if str(actor) == get_settings().dev_actor_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required")
    return actor


@router.get("/me", response_model=UserMe)
async def me(
    session: AsyncSession = Depends(get_session), actor: uuid.UUID = Depends(get_actor)
) -> UserMe:
    """The signed-in caller's own account."""
    _require_signed_in(actor)
    user = await session.get(User, actor)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    return UserMe.model_validate(user, from_attributes=True)


@router.get("/export")
async def export(
    session: AsyncSession = Depends(get_session), actor: uuid.UUID = Depends(get_actor)
) -> dict:
    """A portable JSON archive of everything we hold about the caller (GDPR download)."""
    _require_signed_in(actor)
    archive = await accounts_repo.export_user(session, actor)
    if not archive:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    return archive


@router.get("/uploads", response_model=list[EventRead])
async def my_uploads(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> list[EventRead]:
    """The caller's own uploaded video events, newest upload first (ADR-0029).

    Sourced from the ``activity_log`` (``kind='upload'``) rather than an event column so it
    stays correct even though uploads are authored through the agent pipeline. Includes
    ``pending`` (not-yet-moderated) events so the uploader can see their own submissions.
    """
    _require_signed_in(actor)
    rows = (
        await session.execute(
            text(
                f"SELECT {_EVENT_COLS} FROM events e "
                "JOIN (SELECT target_id, max(created_at) AS up_at FROM activity_log "
                "      WHERE user_id = :uid AND kind = 'upload' AND target_type = 'event' "
                "      GROUP BY target_id) up ON up.target_id = e.id "
                "ORDER BY up.up_at DESC LIMIT :limit"
            ),
            {"uid": actor, "limit": limit},
        )
    ).all()
    return [_event_read(r) for r in rows]


@router.delete("", response_model=PurgeResult)
async def delete_account(
    session: AsyncSession = Depends(get_session), actor: uuid.UUID = Depends(get_actor)
) -> PurgeResult:
    """Irreversibly purge the caller's account and ALL their data (GDPR delete).

    Cascade: identities + agreements (FK), comments, reactions, source-votes, user-authored
    event-links, the user's media links, and a best-effort delete of their object-store
    uploads. See chronos_core.accounts_repo.purge_user.
    """
    _require_signed_in(actor)
    if await session.get(User, actor) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    counts = await accounts_repo.purge_user(session, actor, objectstore=objectstore)
    return PurgeResult(deleted=counts)
