"""Media-gap agent — enforce the no-text-only / clips-first policy (ADR-0023, §4).

An event with no image-kind media is effectively *text-only*: it under-renders and breaks the
"prefer a clip as the hero" article format. ``events_missing_media()`` is the worklist of such
published events; ``flag_media_gaps()`` re-collects each one's subject through the **clip-bearing
/ media-rich** adapters (Wikipedia first) so it gains a hero image and, where available, a clip.

The media floor itself (image required, clip preferred) is the pure
``chronos_core.domain.media_policy.has_required_media`` / ``media_richness`` — this agent just
applies it over the corpus and triggers acquisition.
"""

from __future__ import annotations

import logging

import httpx
from chronos_core import config_service
from chronos_core.db import session_scope
from chronos_core.domain import media_policy
from chronos_core.models.entity import Entity, EventEntity
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.models.media import EventMedia, Media
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_agents.publish import load_weights, publish_candidate
from chronos_agents.sources import registry
from chronos_agents.sources.base import SubjectQuery

log = logging.getLogger("chronos.agents.media_gap")
AGENT = "media-gap"


async def events_missing_media(
    session: AsyncSession, *, limit: int
) -> list[tuple[object, str]]:
    """Published events with **no image-kind** event_media (text-only per ADR-0023).

    Returns ``(event_id, title)`` rows. ``media_policy.has_required_media`` is the floor we
    enforce (>=1 image); this query is its corpus-level inverse."""
    has_image = (
        select(EventMedia.event_id)
        .join(Media, Media.id == EventMedia.media_id)
        .where(EventMedia.event_id == Event.id)
        .where(Media.kind == "image")
    )
    rows = (
        await session.execute(
            select(Event.id, Event.title)
            .where(Event.status == EventStatus.PUBLISHED)
            .where(~exists(has_image))
            .order_by(Event.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [(r[0], r[1]) for r in rows]


async def _subject_for(session: AsyncSession, event_id, title: str) -> SubjectQuery:
    """Build a re-collection subject from the event: its title as the keyword plus a primary
    actor (if any) so media-rich adapters can find a matching, illustrated article."""
    actor = await session.scalar(
        select(Entity.name)
        .select_from(EventEntity)
        .join(Entity, Entity.id == EventEntity.entity_id)
        .where(EventEntity.event_id == event_id)
        .where(EventEntity.role == "actor")
        .limit(1)
    )
    return SubjectQuery(keyword=title, actor=actor)


async def flag_media_gaps() -> dict:
    """Find text-only events and re-collect media for them via the clip-bearing adapters.

    Only media-rich adapters are queried (Wikipedia) so each gap event has the best chance of
    gaining a hero image + clip; new candidates publish through the normal path (the media
    they carry is attached + archived per ADR-0018)."""
    totals = {"candidates": 0, "recollected": 0, "published": 0, "skipped": 0}

    async with session_scope() as session:
        if not await config_service.get(session, "agents.media.gap.enabled", True):
            log.info("media-gap disabled via config")
            return {**totals, "enabled": False}
        batch_size = int(await config_service.get(session, "agents.media.gap.batch_size", 20))
        gaps = await events_missing_media(session, limit=batch_size)
        subjects = [await _subject_for(session, eid, title) for eid, title in gaps]
        adapters = [a for a in await registry.enabled_adapters(session) if a.capabilities.media_rich]
        weights = await load_weights(session)

    totals["candidates"] = len(subjects)
    if not adapters:
        log.info("media-gap: no media-rich adapters enabled — nothing to do")
        return totals

    for subject in subjects:
        if subject.is_empty():
            continue
        for adapter in adapters:
            if not adapter.can_handle(subject):
                continue
            try:
                candidates = await adapter.collect(subject, limit=3)
            except Exception:
                log.exception("media-gap: adapter %s failed for %r", adapter.id, subject.text())
                continue
            for cand in candidates:
                # Only candidates that actually carry an image close the gap.
                images = sum(1 for m in cand.media if m.kind == "image")
                clips = sum(1 for m in cand.media if m.kind in media_policy.CLIP_KINDS)
                if not media_policy.has_required_media(images, clips):
                    continue
                totals["recollected"] += 1
                try:
                    async with session_scope() as session:
                        event = await publish_candidate(
                            session, cand, agent_name=AGENT, weights=weights
                        )
                except Exception:
                    log.exception("media-gap: publish failed for %r", cand.source_url)
                    continue
                totals["published" if event is not None else "skipped"] += 1

    log.info("media-gap done: %s", totals)
    return totals
