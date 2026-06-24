"""Persona-interact engine: AI users react to / comment on / follow each other's content.

Per acting bot: pull recent published events that match its interests (excluding its own posts and
events it already reacted to), ask the local LLM to decide — in the persona's voice — whether to
react (like/important/doubt/dislike), leave a short on-topic comment, and/or follow the author,
then write those via the existing interaction/social repos. Honors the per-bot daily cap and the
global ``bots.*`` switches.

Run:
    python -m chronos_agents.run persona-interact --bot-id <uuid>
    python -m chronos_agents.run persona-interact --count 5
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from chronos_core import bots_repo, config_service, interactions_repo, social_repo
from chronos_core.db import session_scope
from chronos_core.llm import build_router
from chronos_core.models.bot import BotProfile
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.models.interaction import Reaction
from chronos_core.models.media import EventMedia, Media
from chronos_core.models.social import ActivityLog
from chronos_core.models.user import User
from sqlalchemy import func, or_, select

from chronos_agents._json import extract_json_object

log = logging.getLogger("chronos.agents.bots.interact")
AGENT = "persona-interact"

_REACTIONS = {"like", "dislike", "important", "doubt"}
_INTERACT_KINDS = ("like", "comment", "follow")


def _system(bot: BotProfile, user: User) -> str:
    return (
        f"You are {user.display_name}, a social-media user. Tone: {bot.tone or 'neutral'}. "
        f"Interests: {', '.join(bot.interests)}. You are scrolling a world-events video feed. "
        "For the given post, decide how YOU would engage. Return ONLY a JSON object: "
        '{"react": one of ["like","important","doubt","dislike"] or null, '
        '"comment": a short on-topic comment in your voice (<=180 chars) or null, '
        '"follow_author": boolean}. '
        "React/comment only if the post genuinely fits your interests; null is fine. "
        "Comments must be substantive and human — never spammy or generic."
    )


def _user_prompt(event: Event) -> str:
    parts = [f"Title: {event.title}"]
    if event.summary:
        parts.append(f"Summary: {event.summary}")
    if event.category:
        parts.append(f"Category: {event.category}")
    if event.tags:
        parts.append(f"Tags: {', '.join(event.tags)}")
    return "\n".join(parts)


async def _select_bots(session, bot_id, count) -> list[tuple[User, BotProfile]]:
    if bot_id:
        u = await session.get(User, bot_id)
        b = await session.get(BotProfile, bot_id)
        return [(u, b)] if (u and b) else []
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(User, BotProfile)
            .join(BotProfile, BotProfile.user_id == User.id)
            .where(BotProfile.enabled.is_(True), BotProfile.interacts_enabled.is_(True))
            .order_by(BotProfile.last_interact_at.asc().nulls_first())
            .limit(count * 3)
        )
    ).all()
    out = []
    for u, b in rows:
        due = b.last_interact_at is None or (now - b.last_interact_at) >= timedelta(
            minutes=b.interact_cadence_min
        )
        if due:
            out.append((u, b))
        if len(out) >= count:
            break
    return out


async def _candidate_events(session, user: User, bot: BotProfile, limit: int) -> list[Event]:
    """Recent published events matching the bot's interests, not its own, not already reacted to."""
    interests = bot.interests or []
    reacted = select(Reaction.event_id).where(Reaction.user_id == user.id)
    match = or_(
        Event.category.in_(interests),
        Event.tags.overlap(interests),  # ARRAY && — any shared tag
    ) if interests else Event.category.isnot(None)
    stmt = (
        select(Event)
        .where(
            Event.status == EventStatus.PUBLISHED,
            # not its own posts (NULL-safe: most events have a null created_by_agent)
            Event.created_by_agent.is_distinct_from(f"persona:{bot.seed}"),
            match,
            Event.id.notin_(reacted),
        )
        .order_by(Event.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _event_author(session, event_id) -> uuid.UUID | None:
    """The user the hero clip is attributed to (origin_kind='user'), for follow decisions."""
    return await session.scalar(
        select(EventMedia.added_by)
        .join(Media, Media.id == EventMedia.media_id)
        .where(EventMedia.event_id == event_id, EventMedia.role == "hero",
               Media.origin_kind == "user")
        .limit(1)
    )


async def _interactions_today(session, user_id) -> int:
    since = datetime.now(UTC) - timedelta(hours=24)
    return await session.scalar(
        select(func.count()).select_from(ActivityLog).where(
            ActivityLog.user_id == user_id,
            ActivityLog.kind.in_(_INTERACT_KINDS),
            ActivityLog.created_at >= since,
        )
    ) or 0


async def persona_interact(bot_id=None, count: int = 1) -> dict:
    """Have selected bot(s) react/comment/follow on in-interest events. Returns counts."""
    totals = {"selected": 0, "reactions": 0, "comments": 0, "follows": 0, "events_seen": 0}
    async with session_scope() as session:
        await config_service.ensure_defaults(session)
        if not await config_service.get(session, "bots.enabled", True):
            return {"enabled": False}
        if not await config_service.get(session, "bots.interacts_enabled", True):
            return {"interacts_enabled": False}
        per_run = int(await config_service.get(session, "bots.interact.events_per_run", 5))

        selected = await _select_bots(session, bot_id, count)
        totals["selected"] = len(selected)
        if not selected:
            return totals
        router = await build_router(session)
        try:
            for user, bot in selected:
                if not (bot.enabled and bot.interacts_enabled):
                    continue
                budget = bot.daily_interact_cap - await _interactions_today(session, user.id)
                if budget <= 0:
                    continue
                events = await _candidate_events(session, user, bot, per_run)
                rng = random.Random((bot.seed << 4) ^ int(datetime.now(UTC).timestamp()))
                for event in events:
                    if budget <= 0:
                        break
                    totals["events_seen"] += 1
                    decision = await _decide(router, bot, user, event)
                    if decision is None:
                        continue
                    acted = await _apply(session, user, bot, event, decision, rng)
                    for k in ("reactions", "comments", "follows"):
                        totals[k] += acted.get(k, 0)
                    budget -= sum(acted.values())
                if totals["reactions"] or totals["comments"] or totals["follows"]:
                    await session.commit()
        finally:
            await router.aclose()
    log.info("persona-interact: %s", totals)
    return totals


async def _decide(router, bot, user, event) -> dict | None:
    try:
        resp = await router.complete(
            system=_system(bot, user), user=_user_prompt(event), max_tokens=256
        )
        return extract_json_object(resp.text)
    except Exception:
        log.warning("interact decide failed for event %s", event.id, exc_info=True)
        return None


async def _apply(session, user, bot, event, decision: dict, rng) -> dict[str, int]:
    """Write the decided reaction/comment/follow. Returns per-kind action counts."""
    acted = {"reactions": 0, "comments": 0, "follows": 0}

    react = decision.get("react")
    if isinstance(react, str) and react in _REACTIONS:
        added = await interactions_repo.toggle_reaction(
            session, event_id=event.id, user_id=user.id, kind=react
        )
        if added:
            await social_repo.record_activity(
                session, user_id=user.id, kind="like", target_type="event", target_id=event.id
            )
            await bots_repo.bump_interact_stats(session, user.id)
            acted["reactions"] = 1

    comment = decision.get("comment")
    if isinstance(comment, str) and comment.strip():
        await interactions_repo.create_comment(
            session, event_id=event.id, user_id=user.id, body=comment.strip()[:1000]
        )
        await social_repo.record_activity(
            session, user_id=user.id, kind="comment", target_type="event", target_id=event.id
        )
        await bots_repo.bump_interact_stats(session, user.id)
        acted["comments"] = 1

    if decision.get("follow_author"):
        author = await _event_author(session, event.id)
        if author and author != user.id:
            created = await social_repo.follow(
                session, user_id=user.id, target_type="user", target_id=author
            )
            if created:
                await social_repo.record_activity(
                    session, user_id=user.id, kind="follow", target_type="event", target_id=event.id
                )
                await bots_repo.bump_interact_stats(session, user.id)
                acted["follows"] = 1
    return acted
