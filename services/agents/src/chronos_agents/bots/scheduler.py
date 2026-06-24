"""Bot scheduler — the heartbeat that keeps the AI-user feed alive.

One ``bots_tick`` run finds AI users that are *overdue* to post or interact (their per-bot
cadence has elapsed and they're under their daily cap) and enqueues ``persona-post`` /
``persona-interact`` jobs onto the existing Redis run-queue, capped at ``bots.max_concurrent``
per tick so the LLM and feed are never flooded. The worker drains those jobs.

Invoke periodically (e.g. a systemd timer / cron every ~10 min):
    python -m chronos_agents.run bots-tick
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import redis as redislib
from chronos_core import config_service
from chronos_core.db import session_scope
from chronos_core.models.bot import BotProfile
from chronos_core.models.user import User
from chronos_core.run_queue import push_job
from chronos_core.settings import get_settings
from sqlalchemy import select

log = logging.getLogger("chronos.agents.bots.scheduler")
AGENT = "bots-tick"


async def _overdue(session, *, action: str, now: datetime, limit: int) -> list[str]:
    """User ids whose cadence for ``action`` ('post'|'interact') has elapsed."""
    enabled_col = BotProfile.posts_enabled if action == "post" else BotProfile.interacts_enabled
    last_col = BotProfile.last_post_at if action == "post" else BotProfile.last_interact_at
    cadence_col = (
        BotProfile.post_cadence_min if action == "post" else BotProfile.interact_cadence_min
    )
    rows = (
        await session.execute(
            select(BotProfile.user_id, last_col, cadence_col)
            .join(User, User.id == BotProfile.user_id)
            .where(BotProfile.enabled.is_(True), enabled_col.is_(True))
            .order_by(last_col.asc().nulls_first())
            .limit(limit * 4)
        )
    ).all()
    out: list[str] = []
    for user_id, last_at, cadence in rows:
        if last_at is None or (now - last_at) >= timedelta(minutes=cadence):
            out.append(str(user_id))
        if len(out) >= limit:
            break
    return out


async def bots_tick() -> dict:
    """Enqueue post/interact jobs for overdue bots (capped per tick). Returns counts."""
    totals = {"due_post": 0, "due_interact": 0, "enqueued": 0}
    async with session_scope() as session:
        await config_service.ensure_defaults(session)
        if not await config_service.get(session, "bots.enabled", True):
            return {"enabled": False}
        max_concurrent = int(await config_service.get(session, "bots.max_concurrent", 5))
        posts_on = bool(await config_service.get(session, "bots.posts_enabled", True))
        interacts_on = bool(await config_service.get(session, "bots.interacts_enabled", True))
        now = datetime.now(UTC)

        # Split the per-tick budget between posting and interacting.
        post_budget = max_concurrent // 2 if interacts_on else max_concurrent
        interact_budget = max_concurrent - post_budget

        due_post = (
            await _overdue(session, action="post", now=now, limit=post_budget) if posts_on else []
        )
        due_interact = (
            await _overdue(session, action="interact", now=now, limit=interact_budget)
            if interacts_on else []
        )
        totals["due_post"] = len(due_post)
        totals["due_interact"] = len(due_interact)

    r = redislib.from_url(get_settings().redis_url, decode_responses=True)
    try:
        for uid in due_post:
            push_job(r, "persona-post", {"bot_id": uid})
            totals["enqueued"] += 1
        for uid in due_interact:
            push_job(r, "persona-interact", {"bot_id": uid})
            totals["enqueued"] += 1
    finally:
        r.close()

    log.info("bots-tick: %s", totals)
    return totals
