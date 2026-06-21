"""Social graph + promotes + interest profile endpoints (Phase 4-B, ADR-0025/0028).

- POST   /follow            — follow a user|entity|event (write-gated; records activity).
- DELETE /follow            — unfollow.
- GET    /follow/state      — does the caller follow a target? (+ its follower count)
- GET    /follow/followers  — who follows a target.
- GET    /follow/following  — what the caller follows.
- POST   /promote           — promote(+1)/demote(-1)/clear(0) event|relation|source|entity.
- GET    /promote/summary   — aggregate promote tally for a target + the caller's vote.
- GET    /me/interests      — the caller's decayed interest profile (debug/inspection).

Writes resolve the actor through ``require_verified_actor`` (signed-in, email-verified,
agreement accepted — ADR-0026); reads use ``get_actor`` so the caller's own state is reported.
"""

from __future__ import annotations

import uuid

from chronos_core import interest, social_repo as repo
from chronos_core.schemas.event import EventRead
from chronos_core.schemas.social import (
    BookmarkResult,
    FollowCounts,
    FollowList,
    FollowResult,
    FollowTarget,
    InterestProfile,
    PromoteCast,
    PromoteResult,
    PromoteSummary,
)
from chronos_core.settings import get_settings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.auth_stub import get_actor, require_verified_actor
from chronos_api.deps import get_session
from chronos_api.queries import _EVENT_COLS, _event_read

router = APIRouter(tags=["social"])


def _require_signed_in(actor: uuid.UUID) -> uuid.UUID:
    """Reject the dev/anonymous fallback id — a private list needs a real session."""
    if str(actor) == get_settings().dev_actor_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required")
    return actor

_FOLLOW_TARGETS = ("user", "entity", "event")
_PROMOTE_TARGETS = ("event", "relation", "source", "entity")
# Map a follow/promote target to the activity-log target_type (relation→relation, etc.).
_ACTIVITY_TARGET = {"event": "event", "entity": "entity", "source": "source", "relation": "relation"}


# --- follows --------------------------------------------------------------------------


@router.post("/follow", response_model=FollowResult, status_code=status.HTTP_201_CREATED)
async def follow(
    target_type: str = Query(),
    target_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> FollowResult:
    """Follow a user|entity|event (idempotent)."""
    try:
        await repo.follow(session, user_id=actor, target_type=target_type, target_id=target_id)
        if target_type in _ACTIVITY_TARGET:
            await repo.record_activity(
                session, user_id=actor, kind="follow",
                target_type=_ACTIVITY_TARGET[target_type], target_id=target_id,
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return FollowResult(target_type=target_type, target_id=target_id, following=True)


@router.delete("/follow", response_model=FollowResult)
async def unfollow(
    target_type: str = Query(),
    target_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> FollowResult:
    """Unfollow a target (idempotent — reports the post-state)."""
    await repo.unfollow(session, user_id=actor, target_type=target_type, target_id=target_id)
    return FollowResult(target_type=target_type, target_id=target_id, following=False)


@router.get("/follow/state", response_model=FollowResult)
async def follow_state(
    target_type: str = Query(),
    target_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> FollowResult:
    """Whether the caller follows a target."""
    following = await repo.is_following(
        session, user_id=actor, target_type=target_type, target_id=target_id
    )
    return FollowResult(target_type=target_type, target_id=target_id, following=following)


@router.get("/follow/counts", response_model=FollowCounts)
async def follow_counts(
    target_type: str = Query(),
    target_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
) -> FollowCounts:
    """Follower count for a target; for a user target, also their following count."""
    followers = await repo.follower_count(session, target_type=target_type, target_id=target_id)
    following = (
        await repo.following_count(session, user_id=target_id)
        if target_type == "user"
        else 0
    )
    return FollowCounts(
        target_type=target_type, target_id=target_id, followers=followers, following=following
    )


@router.get("/follow/followers", response_model=FollowList)
async def list_followers(
    target_type: str = Query(),
    target_id: uuid.UUID = Query(),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> FollowList:
    """User ids that follow a target (most-recent-first)."""
    ids = await repo.followers(
        session, target_type=target_type, target_id=target_id, limit=limit, offset=offset
    )
    count = await repo.follower_count(session, target_type=target_type, target_id=target_id)
    return FollowList(
        items=[FollowTarget(target_type="user", target_id=i) for i in ids], count=count
    )


@router.get("/follow/following", response_model=FollowList)
async def list_following(
    target_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> FollowList:
    """What the caller follows (optionally filtered by target_type)."""
    edges = await repo.following(
        session, user_id=actor, target_type=target_type, limit=limit, offset=offset
    )
    count = await repo.following_count(session, user_id=actor)
    return FollowList(
        items=[FollowTarget(target_type=t, target_id=i) for t, i in edges], count=count
    )


# --- bookmarks ------------------------------------------------------------------------


@router.post("/bookmark", response_model=BookmarkResult, status_code=status.HTTP_201_CREATED)
async def add_bookmark(
    event_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> BookmarkResult:
    """Save an event to the caller's private collection (idempotent). Private — not logged
    as activity, so it never feeds the interest profile."""
    await repo.bookmark(session, user_id=actor, event_id=event_id)
    return BookmarkResult(event_id=event_id, bookmarked=True)


@router.delete("/bookmark", response_model=BookmarkResult)
async def remove_bookmark(
    event_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> BookmarkResult:
    """Remove a saved event (idempotent — reports the post-state)."""
    await repo.unbookmark(session, user_id=actor, event_id=event_id)
    return BookmarkResult(event_id=event_id, bookmarked=False)


@router.get("/bookmark/state", response_model=BookmarkResult)
async def bookmark_state(
    event_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> BookmarkResult:
    """Whether the caller has the event saved (False when anonymous)."""
    saved = await repo.is_bookmarked(session, user_id=actor, event_id=event_id)
    return BookmarkResult(event_id=event_id, bookmarked=saved)


@router.get("/me/bookmarks", response_model=list[EventRead])
async def my_bookmarks(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> list[EventRead]:
    """The caller's saved events, newest-saved-first (the profile "Saved" tab, FR-3.3)."""
    _require_signed_in(actor)
    rows = (
        await session.execute(
            text(
                f"SELECT {_EVENT_COLS} FROM events e "
                "JOIN bookmarks b ON b.event_id = e.id "
                "WHERE b.user_id = :uid "
                "ORDER BY b.created_at DESC LIMIT :limit"
            ),
            {"uid": actor, "limit": limit},
        )
    ).all()
    return [_event_read(r) for r in rows]


# --- promotes -------------------------------------------------------------------------


@router.post("/promote", response_model=PromoteResult)
async def cast_promote(
    data: PromoteCast,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> PromoteResult:
    """Promote(+1)/demote(-1)/clear(0) an event|relation|source|entity. Returns the fresh
    aggregate."""
    try:
        mine = await repo.cast_promote(
            session, user_id=actor, target_type=data.target_type,
            target_id=data.target_id, value=data.value,
        )
        if data.value != 0:
            await repo.record_activity(
                session, user_id=actor, kind="promote",
                target_type=data.target_type, target_id=data.target_id,
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await session.flush()
    score, up, down = await repo.promote_tally(
        session, target_type=data.target_type, target_id=data.target_id
    )
    return PromoteResult(
        target_type=data.target_type, target_id=data.target_id,
        mine=mine, score=score, up=up, down=down,
    )


@router.get("/promote/summary", response_model=PromoteSummary)
async def promote_summary(
    target_type: str = Query(),
    target_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> PromoteSummary:
    """Aggregate promote tally for a target + the caller's own value."""
    score, up, down = await repo.promote_tally(
        session, target_type=target_type, target_id=target_id
    )
    mine = await repo.my_promote(
        session, user_id=actor, target_type=target_type, target_id=target_id
    )
    return PromoteSummary(
        target_type=target_type, target_id=target_id, score=score, up=up, down=down, mine=mine
    )


# --- interest profile -----------------------------------------------------------------


@router.get("/me/interests", response_model=InterestProfile)
async def my_interests(
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> InterestProfile:
    """The caller's decayed interest profile (debug/inspection of the rec substrate)."""
    return await interest.compute_profile(session, actor)
