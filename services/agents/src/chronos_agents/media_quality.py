"""Media-quality agent (ADR-0024): no low-resolution or media-less cards in the system.

The feed only renders events that have a *displayable* hero, and a hero image must clear a
resolution floor ([wikimedia.MIN_IMAGE_WIDTH]). This agent enforces that over the corpus in
three cheapest-first passes:

  1. **back-fill** — recover each hero image's width from its Wikimedia ``/NNNpx-`` thumb URL
     (no network) and record it, so the quality floor is actually checkable;
  2. **upgrade**   — for events whose hero image is below the floor (or whose width is unknown
     and not a thumb URL), fetch a wider rendition from the article, else **search Commons** for
     a better image, and attach it as the new hero (rank 0);
  3. **fill-gap**  — for events with no hero image at all, search Commons by title and attach a
     high-res one.

Idempotent, best-effort: a network failure on one event never aborts the batch. Events that
still can't get a quality hero simply stay filtered out of the feed (never shown black).
"""

from __future__ import annotations

import logging

import httpx
from chronos_core import config_service, repository
from chronos_core.db import session_scope
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.models.media import EventMedia, Media
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_agents.publish import load_weights
from chronos_agents.sources import wikimedia

log = logging.getLogger("chronos.agents.media_quality")
AGENT = "media-quality"
MIN_W = wikimedia.MIN_IMAGE_WIDTH


async def _backfill_widths(session: AsyncSession) -> int:
    """Pass 1: set width from the thumb URL for image media that have none. No network."""
    rows = (
        await session.execute(
            select(Media.id, Media.source_url).where(
                Media.kind == "image", Media.width.is_(None)
            )
        )
    ).all()
    fixed = 0
    for mid, url in rows:
        w = wikimedia.width_from_thumb_url(url or "")
        if w:
            await session.execute(update(Media).where(Media.id == mid).values(width=w))
            fixed += 1
    return fixed


async def _hero_image(session: AsyncSession, event_id) -> Media | None:
    """The event's current hero image media row (if any)."""
    return await session.scalar(
        select(Media)
        .join(EventMedia, EventMedia.media_id == Media.id)
        .where(EventMedia.event_id == event_id, EventMedia.role == "hero",
               Media.kind == "image")
        .order_by(EventMedia.rank)
        .limit(1)
    )


async def _has_clip_hero(session: AsyncSession, event_id) -> bool:
    return bool(
        await session.scalar(
            select(Media.id)
            .join(EventMedia, EventMedia.media_id == Media.id)
            .where(EventMedia.event_id == event_id, EventMedia.role == "hero",
                   Media.kind.in_(("video", "embed")))
            .limit(1)
        )
    )


async def _first_wiki_source(session: AsyncSession, event_id) -> str | None:
    from chronos_core.models.source import EventSource, Source  # noqa: PLC0415
    return await session.scalar(
        select(Source.url)
        .join(EventSource, EventSource.source_id == Source.id)
        .where(EventSource.event_id == event_id, Source.url.like("%wikipedia.org/wiki/%"))
        .limit(1)
    )


async def _attach_image(session: AsyncSession, event: Event, *, url: str, width: int | None,
                        height: int | None, page_url: str | None, weights) -> None:
    """Attach a quality image as the event's hero (rank 0), recording its dimensions and, when it
    comes from a Commons file page, that page as a source."""
    if page_url:
        source = await repository.get_or_create_source(
            session, url=page_url, title=f"{event.title} (image)",
            publisher="Wikimedia Commons", kind="encyclopedia",
        )
        await repository.link_source(session, event, source, added_by=AGENT, weights=weights)
    await repository.discover_media(
        session, event, url=url, kind="image", role="hero", rank=0,
        width=width, height=height, source_kind="encyclopedia", added_by=AGENT,
    )


async def improve_media(*, batch: int = 200) -> dict:
    """Run the three quality passes over published events. Returns counts."""
    totals = {"width_backfilled": 0, "upgraded": 0, "filled_gap": 0,
              "still_low": 0, "scanned": 0}

    async with session_scope() as session:
        totals["width_backfilled"] = await _backfill_widths(session)
        events = (
            await session.execute(
                select(Event.id, Event.title)
                .where(Event.status == EventStatus.PUBLISHED)
                .order_by(Event.updated_at.desc())
                .limit(batch)
            )
        ).all()
        weights = await load_weights(session)

    async with httpx.AsyncClient(headers={"User-Agent": wikimedia.USER_AGENT}) as client:
        for event_id, title in events:
            totals["scanned"] += 1
            async with session_scope() as session:
                if await _has_clip_hero(session, event_id):
                    continue  # a clip hero already satisfies the floor
                hero = await _hero_image(session, event_id)
                if hero is not None and (hero.width or 0) >= MIN_W:
                    continue  # already good enough
                event = await session.get(Event, event_id)
                src = await _first_wiki_source(session, event_id)

                found = None  # (url, w, h, page_url)
                if src:
                    img = await wikimedia.wiki_image(client, src)
                    if img and (img.width or 0) >= MIN_W:
                        found = (img.url, img.width, img.height, None)
                if found is None:
                    for ci in await wikimedia.commons_images(client, title, limit=3):
                        found = (ci.url, ci.width, ci.height, ci.page_url)
                        break

                if found is None:
                    totals["still_low"] += 1
                    continue
                url, w, h, page_url = found
                await _attach_image(session, event, url=url, width=w, height=h,
                                    page_url=page_url, weights=weights)
                totals["filled_gap" if hero is None else "upgraded"] += 1

    log.info("media-quality done: %s", totals)
    return totals
