"""Persona-post engine: an AI user discovers a free clip in its interests and auto-publishes it.

Per acting bot: pick an interest (weighted) → a topic query → discover license-verified clips →
ask the local LLM to judge relevance/quality and write the post (title/summary/category/tags +
who/where) **in the persona's voice** → publish the best clip that clears the quality bar via
:func:`chronos_core.bot_post.create_bot_video_event`. Clips already posted (same source url) are
skipped. Everything is gated by the global ``bots.*`` switches and the per-bot enable flags.

Run:
    python -m chronos_agents.run persona-post --bot-id <uuid>
    python -m chronos_agents.run persona-post --count 5      # pick overdue bots
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime, timedelta

import httpx
from chronos_core import bots_repo, config_service
from chronos_core.bot_post import create_bot_video_event
from chronos_core.db import session_scope
from chronos_core.llm import build_router
from chronos_core.models.bot import BotProfile
from chronos_core.models.media import Media
from chronos_core.models.social import ActivityLog
from chronos_core.models.user import User
from sqlalchemy import func, select

from chronos_agents._json import extract_json_object
from chronos_agents.bots.discovery import FreeClip, find_free_clips
from chronos_agents.bots.topics import INTEREST_QUERIES, queries_for
from chronos_agents.sources.wikimedia import USER_AGENT

log = logging.getLogger("chronos.agents.bots.post")
AGENT = "persona-post"

_VALID_CATEGORIES = {
    "sports", "science", "news", "politics", "finance", "tech", "history",
    "culture", "nature", "space", "health", "travel",
}


def _system(bot: BotProfile, user: User) -> str:
    return (
        f"You are {user.display_name}, a social-media creator. Tone: {bot.tone or 'neutral'}. "
        f"Interests: {', '.join(bot.interests)}. You are about to post a short video to a "
        "world-events feed. Judge the clip and write the post IN YOUR VOICE. "
        "Return ONLY a JSON object: "
        '{"relevant": boolean, "quality": integer 0-100, "title": string (<=100 chars), '
        '"summary": string (1-2 sentences), "category": one of '
        f"[{', '.join(sorted(_VALID_CATEGORIES))}], "
        '"tags": string[] (2-5 lowercase), "actors": string[] (people/orgs, may be empty), '
        '"locations": string[] (places, may be empty)}. '
        "Set relevant=false if the clip is off-topic for your interests, low quality, or unclear."
    )


def _user_prompt(clip: FreeClip) -> str:
    parts = [f"Clip title: {clip.title}", f"Source: {clip.provider}"]
    if clip.description:
        parts.append(f"Description: {clip.description[:600]}")
    if clip.duration_s:
        parts.append(f"Duration: {clip.duration_s}s")
    return "\n".join(parts)


def _pick_interest(bot: BotProfile, rng: random.Random) -> str:
    weights = bot.interest_weights or {}
    pool = [i for i in bot.interests if i in INTEREST_QUERIES] or bot.interests
    if not pool:
        return "news"
    w = [max(float(weights.get(i, 0)), 0.0001) for i in pool]
    return rng.choices(pool, weights=w, k=1)[0]


async def _already_posted(session, urls: list[str]) -> set[str]:
    if not urls:
        return set()
    rows = (
        await session.execute(
            select(Media.source_url).where(Media.source_url.in_(urls))
        )
    ).scalars().all()
    return set(rows)


async def _posts_today(session, user_id) -> int:
    since = datetime.now(UTC) - timedelta(hours=24)
    return await session.scalar(
        select(func.count()).select_from(ActivityLog).where(
            ActivityLog.user_id == user_id,
            ActivityLog.kind == "upload",
            ActivityLog.created_at >= since,
        )
    ) or 0


async def _select_bots(session, bot_id, count) -> list[tuple[User, BotProfile]]:
    """Resolve the explicit bot, or pick overdue posting bots (cadence honoured)."""
    if bot_id:
        u = await session.get(User, bot_id)
        b = await session.get(BotProfile, bot_id)
        return [(u, b)] if (u and b) else []
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(User, BotProfile)
            .join(BotProfile, BotProfile.user_id == User.id)
            .where(BotProfile.enabled.is_(True), BotProfile.posts_enabled.is_(True))
            .order_by(BotProfile.last_post_at.asc().nulls_first())
            .limit(count * 3)
        )
    ).all()
    out = []
    for u, b in rows:
        due = b.last_post_at is None or (now - b.last_post_at) >= timedelta(
            minutes=b.post_cadence_min
        )
        if due:
            out.append((u, b))
        if len(out) >= count:
            break
    return out


async def persona_post(bot_id=None, count: int = 1) -> dict:
    """Have selected bot(s) each discover + publish one free clip. Returns counts."""
    totals = {"selected": 0, "posted": 0, "skipped": 0, "rejected": 0, "no_clip": 0}
    async with session_scope() as session:
        await config_service.ensure_defaults(session)
        if not await config_service.get(session, "bots.enabled", True):
            return {"enabled": False}
        if not await config_service.get(session, "bots.posts_enabled", True):
            return {"posts_enabled": False}
        floor = int(await config_service.get(session, "bots.global_quality_floor", 50))
        clips_per = int(await config_service.get(session, "bots.post.candidates", 6))

        selected = await _select_bots(session, bot_id, count)
        totals["selected"] = len(selected)
        if not selected:
            return totals
        router = await build_router(session)
        try:
            async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
                for user, bot in selected:
                    # Re-check enable (a job may sit queued after an admin suspend).
                    if not (bot.enabled and bot.posts_enabled):
                        continue
                    if await _posts_today(session, user.id) >= bot.daily_post_cap:
                        totals["skipped"] += 1
                        continue
                    rng = random.Random((bot.seed << 8) ^ int(datetime.now(UTC).timestamp()))
                    interest = _pick_interest(bot, rng)
                    queries = queries_for(interest)
                    query = rng.choice(queries) if queries else interest
                    clips = await find_free_clips(client, session, query, limit=clips_per)
                    if not clips:
                        totals["no_clip"] += 1
                        continue
                    seen = await _already_posted(session, [c.url for c in clips])
                    posted = False
                    for clip in clips:
                        if clip.url in seen:
                            continue
                        threshold = max(bot.quality_threshold, floor)
                        meta = await _judge(router, bot, user, clip)
                        quality = int(meta.get("quality", 0)) if meta else 0
                        if meta is None or not meta.get("relevant") or quality < threshold:
                            totals["rejected"] += 1
                            continue
                        await create_bot_video_event(
                            session,
                            bot_user_id=user.id,
                            seed=bot.seed,
                            title=str(meta.get("title") or clip.title)[:200],
                            summary=str(meta.get("summary") or clip.title),
                            clip_url=clip.url,
                            clip_source_url=clip.source_url,
                            clip_mime=clip.mime,
                            clip_license=clip.license,
                            clip_credit=clip.credit,
                            clip_width=clip.width,
                            clip_height=clip.height,
                            clip_duration_s=clip.duration_s,
                            clip_year=clip.year,
                            category=_clean_category(meta.get("category"), interest),
                            tags=_clean_tags(meta.get("tags"), interest),
                            actor_names=_clean_list(meta.get("actors")),
                            location_names=_clean_list(meta.get("locations")),
                        )
                        await bots_repo.bump_post_stats(session, user.id)
                        await session.commit()
                        totals["posted"] += 1
                        posted = True
                        break
                    if not posted and not clips:
                        totals["no_clip"] += 1
        finally:
            await router.aclose()
    log.info("persona-post: %s", totals)
    return totals


async def _judge(router, bot, user, clip) -> dict | None:
    try:
        resp = await router.complete(
            system=_system(bot, user), user=_user_prompt(clip), max_tokens=512
        )
        return extract_json_object(resp.text)
    except Exception:
        log.warning("judge failed for clip %s", clip.url, exc_info=True)
        return None


def _clean_category(value, fallback: str) -> str:
    v = (value or "").strip().lower() if isinstance(value, str) else ""
    return v if v in _VALID_CATEGORIES else fallback


def _clean_tags(value, interest: str) -> list[str]:
    raw = value if isinstance(value, list) else []
    tags = [str(t).strip().lower()[:24] for t in raw if str(t).strip()]
    if interest not in tags:
        tags.append(interest)
    return list(dict.fromkeys(tags))[:5]


def _clean_list(value) -> list[str]:
    raw = value if isinstance(value, list) else []
    return [str(x).strip()[:80] for x in raw if str(x).strip()][:4]
