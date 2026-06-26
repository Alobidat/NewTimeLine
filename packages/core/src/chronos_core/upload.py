"""User-generated video event upload (ADR-0029 + the ADR-0020 every-event invariant).

Pure DB/storage logic shared by the upload router (and reusable by a future transcode
worker). One call (:func:`create_video_event`) takes the validated metadata + the stored
binary's object-store key and:

1. creates the ``event`` (status ``pending`` moderation) via chronos_core.repository,
2. creates the **hero** ``media`` (kind=video, status=stored) + links it to the event,
3. tags ``actor`` entities and a ``location`` entity (the ADR-0020 who/where),
4. sets ``geom`` directly when explicit coordinates were given,
5. records the user's ``event_relations`` links to the events they referenced,
6. records an ``upload`` activity row.

Required-metadata enforcement (time + location + actors + at least the supplied links) lives
in the schema/router (400 on missing); this layer assumes a validated payload. The binary is
stored by the **router** (which owns the object-store call + size/type limits); we only take
the resulting key so this module stays free of network/IO and is unit-testable. Caller commits.

Moderation is a status stub: events land ``pending`` and the hero media is ``stored`` but the
event is held out of the public feed until promoted to ``visible`` (a later moderation pass).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core import repository
from chronos_core.models.enums import EventStatus, EventVisibility
from chronos_core.models.event import Event
from chronos_core.models.media import EventMedia, Media
from chronos_core.schemas.event import EventCreate, GeoPoint

AGENT = "upload"


async def create_video_event(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str,
    t_start: float,
    storage_key: str,
    mime: str,
    bytes_len: int,
    summary: str | None = None,
    time_precision: str | None = None,
    instant=None,
    geo: GeoPoint | None = None,
    geo_label: str | None = None,
    actor_names: list[str],
    location_names: list[str] | None = None,
    link_event_ids: list[uuid.UUID],
    duration_s: int | None = None,
    width: int | None = None,
    height: int | None = None,
    category: str | None = None,
    visibility: str | None = None,
    edit_spec: dict | None = None,
) -> Event:
    """Create a **published** user video event with its hero clip + metadata, at the chosen
    audience ``visibility`` (public|followers|friends). Caller commits."""
    by = str(user_id)
    create = EventCreate(
        title=title,
        summary=summary,
        t_start=t_start,
        time_precision=time_precision or "day",
        instant=instant,
        category=category or "user",
        geo=geo,
        geo_label=geo_label,
        created_by_agent=AGENT,
    )
    event = await repository.create_event(session, create)
    # Auto-publish (Phase 4): the post is live immediately; an async LLM pass (Phase 6) may
    # flag it for the admin queue afterward. Audience controls who can see it.
    event.status = EventStatus.PUBLISHED
    event.visibility = EventVisibility(visibility) if visibility else EventVisibility.PUBLIC
    await session.flush()

    # Hero video media (already stored in the object store by the router).
    media = Media(
        kind="video",
        storage_key=storage_key,
        mime=mime,
        bytes=bytes_len,
        duration_s=duration_s,
        width=width,
        height=height,
        status="stored",
        disposition="pin",          # user uploads are pinned (we own the only copy)
        origin_kind="user",
        added_by=by,
        edit_spec=edit_spec,        # transcode applies trim/speed when building the web variant
    )
    session.add(media)
    await session.flush()
    session.add(
        EventMedia(event_id=event.id, media_id=media.id, role="hero", rank=0, added_by=by)
    )

    # Actors + location entities → the ADR-0020 who/where invariant.
    for name in actor_names:
        if not name.strip():
            continue
        entity = await repository.get_or_create_entity(session, kind="person", name=name)
        await repository.link_entity(session, event, entity, role="actor", added_by=by)
    for name in location_names or []:
        if not name.strip():
            continue
        entity = await repository.get_or_create_entity(session, kind="place", name=name)
        await repository.link_entity(session, event, entity, role="location", added_by=by)

    # User-asserted links to the events they referenced (a thematic edge each, both directions
    # are not assumed — the user said "this relates to X" → new event → X).
    for dst in link_event_ids:
        if dst == event.id:
            continue
        await repository.link_relation(
            session, src_event=event.id, dst_event=dst, kind="thematic", created_by=by
        )

    await _record_upload_activity(session, user_id, event.id)
    return event


async def _record_upload_activity(
    session: AsyncSession, user_id: uuid.UUID, event_id: uuid.UUID
) -> None:
    """Best-effort upload activity (import-local to avoid a core import cycle at module load)."""
    from chronos_core import social_repo

    await social_repo.record_activity(
        session, user_id=user_id, kind="upload", target_type="event", target_id=event_id
    )
