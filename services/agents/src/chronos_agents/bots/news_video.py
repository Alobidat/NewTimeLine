"""News-anchor agent: find the latest hot story → generate a short video for it via ComfyUI →
publish it to the feed under a dedicated AI-anchor persona's profile.

The loop (per run):
  1. ensure the **Chronos Newsreel** bot persona exists (idempotent, fixed seed),
  2. pick the hottest recent RSS-ingested news event the anchor hasn't covered yet,
  3. ask the LLM (in the anchor's voice) to turn the headline into a vivid text-to-video prompt
     plus a post title/summary/who/where,
  4. render a clip with LTX-Video on the GPU box ([chronos_agents.comfyui]),
  5. store the mp4 in the object store and publish a bot video event linked to the source story
     ([chronos_core.bot_post.create_bot_generated_video_event]).

Run:
    python -m chronos_agents.run news-video               # cover the top hot story
    python -m chronos_agents.run news-video --count 3     # up to 3 stories
    python -m chronos_agents.run news-video --dry-run     # find + prompt, skip render/publish
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from chronos_core import bots_repo, config_service, objectstore
from chronos_core.bot_post import create_bot_generated_video_event
from chronos_core.db import session_scope
from chronos_core.llm import build_router
from chronos_core.models.enums import EventStatus, EventVisibility
from chronos_core.models.event import Event
from chronos_core.models.relation import EventRelation
from sqlalchemy import select
from sqlalchemy.orm import aliased

from chronos_agents import comfyui
from chronos_agents._json import extract_json_object

log = logging.getLogger("chronos.agents.bots.news_video")
AGENT = "news-video"
COMPONENT = "agent:bots.news_video"

# Fixed, high seed so the anchor never collides with the generated persona roster (small seeds).
ANCHOR_SEED = 990001
ANCHOR_TAG = f"persona:{ANCHOR_SEED}"
_NEWS_AGENT = "ingest:rss"  # created_by_agent of RSS-ingested news events (the hot-story source)

_VALID_CATEGORIES = {
    "news", "politics", "finance", "tech", "science", "health", "sports", "culture", "nature",
    "space", "travel", "history",
}


async def _ensure_anchor(session):
    """Create (idempotently) the dedicated news-anchor bot persona; return (user, profile)."""
    return await bots_repo.create_bot(
        session,
        seed=ANCHOR_SEED,
        handle="newsreel",
        display_name="Chronos Newsreel",
        avatar_url=None,
        persona=(
            "An AI news anchor for Chronos. Watches the world's headlines and turns each "
            "breaking story into a short, cinematic video dispatch."
        ),
        interests=["news", "politics", "world", "tech", "science"],
        interest_weights={"news": 1.0, "politics": 0.6, "tech": 0.5, "science": 0.5},
        tone="crisp, authoritative, vivid",
        post_cadence_min=120,
        daily_post_cap=24,
    )


async def _find_hot_story(session, *, since_days: int, exclude: set[uuid.UUID]):
    """The hottest recent news event the anchor hasn't already covered (nor in ``exclude``)."""
    since = datetime.now(UTC) - timedelta(days=since_days)
    anchor_evt = aliased(Event)
    covered = (
        select(EventRelation.dst_event)
        .join(anchor_evt, anchor_evt.id == EventRelation.src_event)
        .where(anchor_evt.created_by_agent == ANCHOR_TAG)
    )
    q = (
        select(Event)
        .where(
            Event.created_by_agent == _NEWS_AGENT,
            Event.status == EventStatus.PUBLISHED,
            Event.visibility == EventVisibility.PUBLIC,
            Event.created_at >= since,
            Event.id.notin_(covered),
        )
        .order_by(
            Event.source_count.desc(), Event.severity.desc(), Event.created_at.desc()
        )
        .limit(8)
    )
    for ev in (await session.execute(q)).scalars().all():
        if ev.id not in exclude:
            return ev
    return None


def _anchor_system(display_name: str) -> str:
    return (
        f"You are {display_name}, an AI news anchor producing short cinematic video dispatches for "
        "a world-events feed. Given a breaking-news headline, write a vivid TEXT-TO-VIDEO prompt "
        "that visually represents the story: one concrete scene, real setting, camera motion, "
        "lighting and mood — NO on-screen text, logos, captions, or watermarks. Then write the "
        "post in your voice. Return ONLY a JSON object: "
        '{"video_prompt": string (<=400 chars, the scene to render), '
        '"title": string (<=100 chars), "summary": string (1-2 sentences), '
        f'"category": one of [{", ".join(sorted(_VALID_CATEGORIES))}], '
        '"actors": string[] (key people/orgs, may be empty), '
        '"locations": string[] (places, may be empty)}.'
    )


async def _compose(router, display_name: str, story: Event) -> dict | None:
    user = f"Headline: {story.title}"
    if story.summary:
        user += f"\nSummary: {story.summary[:600]}"
    try:
        resp = await router.complete(
            system=_anchor_system(display_name), user=user, max_tokens=600
        )
        return extract_json_object(resp.text)
    except Exception:
        log.warning("news-video: compose failed for %s", story.id, exc_info=True)
        return None


def _fallback_compose(story: Event) -> dict:
    """If the LLM is unavailable, render a generic but on-topic cinematic b-roll of the headline."""
    return {
        "video_prompt": (
            f"cinematic documentary b-roll representing the news story: {story.title}. "
            "realistic scene, dramatic natural lighting, slow smooth camera motion, "
            "broadcast quality, highly detailed"
        ),
        "title": story.title[:100],
        "summary": (story.summary or story.title)[:280],
        "category": "news",
        "actors": [],
        "locations": [],
    }


def _clean_list(value) -> list[str]:
    raw = value if isinstance(value, list) else []
    return [str(x).strip()[:80] for x in raw if str(x).strip()][:4]


def _clean_category(value) -> str:
    v = (value or "").strip().lower() if isinstance(value, str) else ""
    return v if v in _VALID_CATEGORIES else "news"


async def generate_news_video(*, count: int = 1, story_id: str | None = None,
                              dry_run: bool = False) -> dict:
    """Find hot stories, render a video for each, and post them under the anchor. Returns counts."""
    totals = {"selected": 0, "rendered": 0, "posted": 0, "no_story": 0, "failed": 0}
    async with session_scope() as session:
        await config_service.ensure_defaults(session)
        if not await config_service.get(session, "agents.news_video.enabled", True):
            return {"enabled": False}
        base_url = await config_service.get(session, "agents.comfyui.base_url", "")
        if not base_url:
            log.warning("news-video: no agents.comfyui.base_url configured")
            return {"comfyui": "unconfigured"}
        timeout_s = int(await config_service.get(session, "agents.comfyui.timeout_seconds", 600))
        seconds = float(await config_service.get(session, "agents.news_video.seconds", 4.0))
        steps = int(await config_service.get(session, "agents.news_video.steps", 20))
        since_days = int(await config_service.get(session, "agents.news_video.since_days", 7))

        anchor_user, anchor_bot = await _ensure_anchor(session)
        await session.commit()
        router = await build_router(session)

        seen: set[uuid.UUID] = set()
        try:
            for _ in range(max(count, 1)):
                if story_id:
                    story = await session.get(Event, uuid.UUID(story_id))
                    story_id = None  # only the first iteration honours the explicit id
                else:
                    story = await _find_hot_story(session, since_days=since_days, exclude=seen)
                if story is None:
                    totals["no_story"] += 1
                    break
                seen.add(story.id)
                totals["selected"] += 1

                meta = await _compose(router, anchor_user.display_name, story) \
                    or _fallback_compose(story)
                vprompt = str(meta.get("video_prompt") or "").strip() \
                    or _fallback_compose(story)["video_prompt"]
                log.info("news-video: story=%s prompt=%r", story.id, vprompt[:120])
                if dry_run:
                    continue

                out = await comfyui.generate_video(
                    base_url, vprompt, seconds=seconds, steps=steps,
                    seed=random.randint(1, 2**31 - 1), timeout_s=timeout_s,
                )
                if not out:
                    totals["failed"] += 1
                    continue
                data, width, height, frames = out
                totals["rendered"] += 1

                storage_key = f"news-video/{uuid.uuid4().hex}.mp4"
                await asyncio.to_thread(
                    objectstore.put_bytes, storage_key, data, content_type="video/mp4"
                )
                await create_bot_generated_video_event(
                    session,
                    bot_user_id=anchor_user.id,
                    seed=ANCHOR_SEED,
                    title=str(meta.get("title") or story.title)[:200],
                    summary=str(meta.get("summary") or story.summary or story.title),
                    storage_key=storage_key,
                    mime="video/mp4",
                    bytes_len=len(data),
                    width=width,
                    height=height,
                    duration_s=max(round(frames / comfyui.LTXV_FPS), 1),
                    t_start=story.t_start,
                    category=_clean_category(meta.get("category")),
                    tags=["news", "ai-generated"],
                    actor_names=_clean_list(meta.get("actors")),
                    location_names=_clean_list(meta.get("locations")),
                    link_event_ids=[story.id],
                )
                await bots_repo.bump_post_stats(session, anchor_user.id)
                await session.commit()
                totals["posted"] += 1
        finally:
            await router.aclose()
    log.info("news-video: %s", totals)
    return totals
