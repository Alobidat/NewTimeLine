"""Admin API for AI users (bot personas) — the roster + per-bot controls (ADR: AI users).

Sits under the same ``/admin`` prefix + ``require_admin`` gate as the generic component admin,
but is data-row oriented (hundreds of bots) rather than component-manifest oriented: list/inspect
individual bots, tune their cadence/caps/threshold, suspend them, kick a one-off post/interact
job, retract a bot post, and bulk-bootstrap a roster. Per-bot run-now + bootstrap enqueue jobs
onto the same Redis run-queue the worker drains.
"""

from __future__ import annotations

import uuid

import redis as redislib
from chronos_core import bots_repo, social_repo
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.models.interaction import Comment
from chronos_core.models.media import EventMedia
from chronos_core.run_queue import push_job
from chronos_core.schemas.admin_bots import (
    ActionResult,
    BootstrapRequest,
    BotCommentView,
    BotDetail,
    BotPostView,
    BotRoster,
    BotUpdate,
    BotView,
)
from chronos_core.settings import get_settings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session, require_admin

router = APIRouter(
    prefix="/admin/bots", tags=["admin", "bots"], dependencies=[Depends(require_admin)]
)


def _view(user, bot) -> BotView:
    return BotView(
        id=user.id, handle=user.handle, display_name=user.display_name,
        avatar_url=user.avatar_url, interests=bot.interests, tone=bot.tone,
        enabled=bot.enabled, posts_enabled=bot.posts_enabled,
        interacts_enabled=bot.interacts_enabled, posts_count=bot.posts_count,
        interactions_count=bot.interactions_count, last_post_at=bot.last_post_at,
        last_interact_at=bot.last_interact_at, created_at=bot.created_at,
    )


@router.get("", response_model=BotRoster)
async def list_bots(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> BotRoster:
    """The AI-users roster (newest first) + totals."""
    rows = await bots_repo.list_bots(session, limit=limit, offset=offset)
    total = await bots_repo.count_bots(session)
    enabled = await bots_repo.count_bots(session, enabled=True)
    return BotRoster(total=total, enabled=enabled, bots=[_view(u, b) for u, b in rows])


@router.get("/{bot_id}", response_model=BotDetail)
async def bot_detail(
    bot_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> BotDetail:
    """One bot: persona + behaviour config + recent posts/comments + graph counts."""
    bot = await bots_repo.get_bot(session, bot_id)
    user = await social_repo.get_user(session, bot_id)
    if bot is None or user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown bot")

    posts = (
        await session.execute(
            select(Event)
            .join(EventMedia, EventMedia.event_id == Event.id)
            .where(EventMedia.added_by == str(bot_id), EventMedia.role == "hero")
            .order_by(desc(Event.created_at))
            .limit(10)
        )
    ).scalars().all()
    comments = (
        await session.execute(
            select(Comment).where(Comment.user_id == bot_id)
            .order_by(desc(Comment.created_at)).limit(10)
        )
    ).scalars().all()

    base = _view(user, bot)
    return BotDetail(
        **base.model_dump(),
        persona=bot.persona, interest_weights=bot.interest_weights,
        post_cadence_min=bot.post_cadence_min, interact_cadence_min=bot.interact_cadence_min,
        quality_threshold=bot.quality_threshold, daily_post_cap=bot.daily_post_cap,
        daily_interact_cap=bot.daily_interact_cap, seed=bot.seed,
        followers=await social_repo.follower_count(session, target_type="user", target_id=bot_id),
        following=await social_repo.following_count(session, user_id=bot_id),
        recent_posts=[
            BotPostView(event_id=e.id, title=e.title, status=str(e.status.value),
                        category=e.category, created_at=e.created_at)
            for e in posts
        ],
        recent_comments=[
            BotCommentView(event_id=c.event_id, body=c.body, created_at=c.created_at)
            for c in comments
        ],
    )


@router.patch("/{bot_id}", response_model=BotView)
async def update_bot(
    bot_id: uuid.UUID, body: BotUpdate, session: AsyncSession = Depends(get_session)
) -> BotView:
    """Tune a bot's enable flags / cadence / caps / quality threshold."""
    await bots_repo.set_enabled(
        session, bot_id, enabled=body.enabled, posts_enabled=body.posts_enabled,
        interacts_enabled=body.interacts_enabled,
    )
    await bots_repo.update_config(
        session, bot_id, post_cadence_min=body.post_cadence_min,
        interact_cadence_min=body.interact_cadence_min, quality_threshold=body.quality_threshold,
        daily_post_cap=body.daily_post_cap, daily_interact_cap=body.daily_interact_cap,
    )
    bot = await bots_repo.get_bot(session, bot_id)
    user = await social_repo.get_user(session, bot_id)
    if bot is None or user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown bot")
    await session.commit()
    return _view(user, bot)


@router.post("/{bot_id}/actions/{action}", response_model=ActionResult)
async def bot_action(bot_id: uuid.UUID, action: str) -> ActionResult:
    """Kick a one-off ``post`` or ``interact`` job for this bot (enqueued to the worker)."""
    command = {"post": "persona-post", "interact": "persona-interact"}.get(action)
    if command is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action must be post|interact")
    r = redislib.from_url(get_settings().redis_url, decode_responses=True)
    try:
        push_job(r, command, {"bot_id": str(bot_id)})
    finally:
        r.close()
    return ActionResult(ok=True, detail=f"enqueued {command}")


@router.post("/posts/{event_id}/retract", response_model=ActionResult)
async def retract_post(
    event_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ActionResult:
    """Pull a bot post from every feed (status → retracted)."""
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown event")
    event.status = EventStatus.RETRACTED
    await session.commit()
    return ActionResult(ok=True, detail="retracted")


@router.post("/bootstrap", response_model=ActionResult)
async def bootstrap(body: BootstrapRequest) -> ActionResult:
    """Enqueue a bulk bootstrap (create N personas + seed posts) for the worker to run."""
    r = redislib.from_url(get_settings().redis_url, decode_responses=True)
    try:
        push_job(r, "bots-bootstrap", {"count": body.count, "posts_per_bot": body.posts_per_bot})
    finally:
        r.close()
    return ActionResult(ok=True, detail=f"bootstrap of {body.count} enqueued")
