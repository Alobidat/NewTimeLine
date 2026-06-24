"""Auto-published video event for an AI user (the bot sibling of :mod:`chronos_core.upload`).

``upload.create_video_event`` hard-codes ``status=PENDING`` and needs a binary already in the
object store (a human upload). A bot instead discovers a **remote, free-licensed** clip, so this
sibling:

- publishes immediately (``status=PUBLISHED``) — bot content is gated by the LLM quality check in
  the post agent, not a moderation queue;
- attaches the discovered clip as the hero ``media`` with ``embed_url`` (plays instantly via the
  ``/media/{id}/raw`` proxy) **and** ``status="pending"`` + ``disposition="pin"`` so the existing
  ``media-fetch`` agent captures the bytes into MinIO (dedupe + thumbnail) — reusing that pipeline;
- sets the hero media ``origin_kind="user"`` + ``added_by=<bot id>`` so the feed's author join
  attributes the post to the bot persona (``feed_queries._HERO_JOIN``);
- records the clip's verified ``license``/``credit`` on the media row for on-card credit + audit.

Caller commits.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core import repository
from chronos_core.domain.temporal import datetime_to_t
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.models.media import EventMedia, Media
from chronos_core.schemas.event import EventCreate, GeoPoint


async def create_bot_video_event(
    session: AsyncSession,
    *,
    bot_user_id: uuid.UUID,
    seed: int,
    title: str,
    summary: str,
    clip_url: str,
    clip_source_url: str,
    clip_mime: str = "video/mp4",
    clip_license: str | None = None,
    clip_credit: str | None = None,
    clip_width: int | None = None,
    clip_height: int | None = None,
    clip_duration_s: int | None = None,
    clip_year: float | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    actor_names: list[str] | None = None,
    location_names: list[str] | None = None,
    geo: GeoPoint | None = None,
    geo_label: str | None = None,
) -> Event:
    """Create + publish a bot-authored video event with its hero clip. Caller commits."""
    by = str(bot_user_id)
    now = datetime.now(UTC)
    # Place the post in the timeline at the clip's own year when known (so the relate agent links
    # it into the history graph — the same integration that surfaces the seed_video clips); a
    # clip with no known date is a present-day post.
    if clip_year:
        t_start, precision, instant = float(clip_year), "year", None
    else:
        t_start, precision, instant = datetime_to_t(now), "day", now

    event = await repository.create_event(
        session,
        EventCreate(
            title=title[:200],
            summary=summary or None,
            t_start=t_start,
            time_precision=precision,
            instant=instant,
            category=category or "user",
            tags=tags or [],
            geo=geo,
            geo_label=geo_label,
            created_by_agent=f"persona:{seed}",
        ),
    )
    event.status = EventStatus.PUBLISHED
    await session.flush()

    # Provenance source (the clip's page) — best-effort; not required for feed visibility.
    if clip_source_url:
        source = await repository.get_or_create_source(
            session, url=clip_source_url, title=title[:200],
            # publisher is varchar(255); a Commons "Artist" credit can be long.
            publisher=(clip_credit[:200] if clip_credit else None), kind="video",
        )
        await repository.link_source(session, event, source, added_by=by)

    # Hero clip: plays now via embed_url; media-fetch captures it (pending + pin); attributed to
    # the bot via origin_kind='user' + added_by so the feed author join lights up.
    media = Media(
        kind="video",
        source_url=clip_url,
        embed_url=clip_url,
        mime=clip_mime,
        width=clip_width,
        height=clip_height,
        duration_s=clip_duration_s,
        license=(clip_license or None) and clip_license[:64],
        credit=(clip_credit or None) and clip_credit[:200],
        status="pending",
        disposition="pin",
        origin_kind="user",
        added_by=by,
    )
    session.add(media)
    await session.flush()
    session.add(
        EventMedia(event_id=event.id, media_id=media.id, role="hero", rank=0, added_by=by)
    )

    # who/where entities (ADR-0020) — anchor the post in the history graph for relate + interest.
    for name in actor_names or []:
        if name and name.strip():
            entity = await repository.get_or_create_entity(
                session, kind="person", name=name.strip()
            )
            await repository.link_entity(session, event, entity, role="actor", added_by=by)
    for name in location_names or []:
        if name and name.strip():
            entity = await repository.get_or_create_entity(
                session, kind="place", name=name.strip()
            )
            await repository.link_entity(session, event, entity, role="location", added_by=by)

    await _record_upload_activity(session, bot_user_id, event.id)
    return event


async def _record_upload_activity(
    session: AsyncSession, user_id: uuid.UUID, event_id: uuid.UUID
) -> None:
    from chronos_core import social_repo

    await social_repo.record_activity(
        session, user_id=user_id, kind="upload", target_type="event", target_id=event_id
    )
