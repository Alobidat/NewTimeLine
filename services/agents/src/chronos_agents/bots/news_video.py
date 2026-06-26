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

from chronos_agents import comfyui, tts
from chronos_agents._json import extract_json_object
from chronos_agents.bots import news_video_render

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


def _anchor_system(display_name: str, scenes: int) -> str:
    return (
        f"You are {display_name}, an AI news anchor producing a short, INFORMATIVE video dispatch "
        "that summarizes a breaking story for a world-events feed. Given the headline + summary, "
        "produce a tight script. Return ONLY a JSON object: "
        '{"title": string (<=90 chars, punchy), '
        '"summary": string (1-2 sentences), '
        '"narration": string (the spoken voiceover: '
        f'{scenes} short, factual, information-dense sentences that actually summarize the story — '
        'no fluff, no "in this video"), '
        f'"scenes": array of exactly {scenes} objects, each '
        '{"visual": string (a concrete photojournalistic IMAGE prompt for this beat — real '
        'setting, subjects, lighting; documentary news photography; NO text/logos/watermarks), '
        '"caption": string (<=70 chars, an on-screen key fact for this beat)}, '
        f'"category": one of [{", ".join(sorted(_VALID_CATEGORIES))}], '
        '"actors": string[] (key people/orgs, may be empty), '
        '"locations": string[] (places, may be empty)}. '
        "The narration sentences and the scene captions should track the same beats in order."
    )


async def _compose(router, display_name: str, story: Event, scenes: int) -> dict | None:
    user = f"Headline: {story.title}"
    if story.summary:
        user += f"\nSummary: {story.summary[:800]}"
    try:
        resp = await router.complete(
            system=_anchor_system(display_name, scenes), user=user, max_tokens=2000
        )
        return extract_json_object(resp.text)
    except Exception:
        log.warning("news-video: compose failed for %s", story.id, exc_info=True)
        return None


def _fallback_compose(story: Event, scenes: int) -> dict:
    """If the LLM is unavailable, build a minimal but on-topic explainer from the headline."""
    head = story.title.strip()
    summary = (story.summary or head).strip()
    visual = (f"photojournalistic documentary photo representing the news story: {head}. "
              "real setting, dramatic natural light, sharp focus, news photography")
    return {
        "title": head[:90],
        "summary": summary[:280],
        "narration": summary,
        "scenes": [{"visual": visual, "caption": head[:70]} for _ in range(max(scenes, 1))],
        "category": "news",
        "actors": [],
        "locations": [],
    }


def _clean_scenes(value, *, limit: int) -> list[dict]:
    """Sanitize the LLM 'scenes' into a bounded list of {visual, caption} with non-empty visuals."""
    out: list[dict] = []
    for s in value if isinstance(value, list) else []:
        if not isinstance(s, dict):
            continue
        visual = str(s.get("visual") or "").strip()
        if not visual:
            continue
        caption = str(s.get("caption") or "").strip()[:90]
        out.append({"visual": visual[:400], "caption": caption})
        if len(out) >= limit:
            break
    return out


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
        n_scenes = int(await config_service.get(session, "agents.news_video.scenes", 5))
        img_steps = int(await config_service.get(session, "agents.news_video.image_steps", 30))
        img_w = int(await config_service.get(session, "agents.news_video.image_width", 832))
        img_h = int(await config_service.get(session, "agents.news_video.image_height", 1216))
        since_days = int(await config_service.get(session, "agents.news_video.since_days", 7))
        tts_enabled = bool(await config_service.get(session, "agents.news_video.tts_enabled", True))
        voice_model = await config_service.get(
            session, "agents.news_video.voice_model", "/opt/piper/en_US-amy-medium.onnx"
        )

        anchor_user, _anchor_bot = await _ensure_anchor(session)
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

                meta = await _compose(router, anchor_user.display_name, story, n_scenes) \
                    or _fallback_compose(story, n_scenes)
                scenes = _clean_scenes(meta.get("scenes"), limit=n_scenes) \
                    or _fallback_compose(story, n_scenes)["scenes"]
                title = str(meta.get("title") or story.title)[:200]
                narration = str(meta.get("narration") or meta.get("summary") or story.title)
                log.info("news-video: story=%s scenes=%d title=%r",
                         story.id, len(scenes), title[:80])
                if dry_run:
                    continue

                # 1) render an image per scene on the GPU box (sequential — one card)
                images: list[tuple[bytes, str]] = []
                for sc in scenes:
                    img = await comfyui.generate_image(
                        base_url, sc["visual"], width=img_w, height=img_h, steps=img_steps,
                        seed=random.randint(1, 2**31 - 1), timeout_s=timeout_s,
                    )
                    if img:
                        images.append((img, sc["caption"]))
                if not images:
                    totals["failed"] += 1
                    continue

                # 2) narration (offline TTS) + 3) compose the captioned explainer (ffmpeg on worker)
                narration_wav = (
                    await asyncio.to_thread(tts.synthesize, narration, model_path=voice_model)
                    if tts_enabled else None
                )
                out = await asyncio.to_thread(
                    news_video_render.render, images, title, narration_wav
                )
                if not out:
                    totals["failed"] += 1
                    continue
                data, duration_s = out
                totals["rendered"] += 1

                storage_key = f"news-video/{uuid.uuid4().hex}.mp4"
                await asyncio.to_thread(
                    objectstore.put_bytes, storage_key, data, content_type="video/mp4"
                )
                await create_bot_generated_video_event(
                    session,
                    bot_user_id=anchor_user.id,
                    seed=ANCHOR_SEED,
                    title=title,
                    summary=str(meta.get("summary") or story.summary or story.title),
                    storage_key=storage_key,
                    mime="video/mp4",
                    bytes_len=len(data),
                    width=news_video_render.WIDTH,
                    height=news_video_render.HEIGHT,
                    duration_s=duration_s,
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
