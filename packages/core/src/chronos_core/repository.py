"""Write helpers shared by the API and the agents (so event-write logic lives in one place).

Reads with PostGIS projections live in the API (chronos_api.queries); these are the
mutations: create an event, attach a source, refresh derived severity/confidence.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.domain import media_policy
from chronos_core.domain.entities import entity_name_key
from chronos_core.domain.severity import (
    SeverityWeights,
    compute_severity,
    normalize_corroboration,
)
from chronos_core.domain.temporal import materialize_span
from chronos_core.models.entity import Entity, EventEntity
from chronos_core.models.event import Event, EventReference
from chronos_core.models.media import EventMedia, Media, MediaSource
from chronos_core.models.relation import EventRelation
from chronos_core.models.source import EventSource, Source
from chronos_core.schemas.enrichment import EnrichmentResult
from chronos_core.schemas.event import EventCreate, GeoPoint

_ENTITY_KINDS = {"person", "org", "place", "topic"}
_ENTITY_ROLES = {"actor", "location", "subject", "affected"}


def _point_expr(geo: GeoPoint | None):
    """SQL expression for a WGS84 point, or None."""
    if geo is None:
        return None
    return func.ST_SetSRID(func.ST_MakePoint(geo.lon, geo.lat), 4326)


def _derive_scores(source_count: int, weights: SeverityWeights | None):
    """Compute severity + confidence from current signals (Phase 1: corroboration only)."""
    sev = compute_severity(source_count=source_count, weights=weights)
    confidence = round(normalize_corroboration(source_count) * 100)
    return sev, confidence


async def create_event(
    session: AsyncSession,
    data: EventCreate,
    *,
    source_count: int = 0,
    weights: SeverityWeights | None = None,
) -> Event:
    """Insert an event, materializing ``t_end`` and derived scores. Caller commits."""
    t_start, t_end = materialize_span(data.t_start, data.time_precision, data.t_end)
    sev, confidence = _derive_scores(source_count, weights)
    event = Event(
        title=data.title,
        summary=data.summary,
        body=data.body,
        t_start=t_start,
        t_end=t_end,
        time_precision=data.time_precision,
        instant=data.instant,
        category=data.category,
        tags=data.tags,
        geom=_point_expr(data.geo),
        geo_label=data.geo_label,
        severity=sev.score,
        severity_breakdown={
            "impact": sev.impact,
            "social": sev.social,
            "corroboration": sev.corroboration,
        },
        confidence=confidence,
        source_count=source_count,
        created_by_agent=data.created_by_agent,
    )
    session.add(event)
    await session.flush()
    return event


async def get_or_create_source(
    session: AsyncSession,
    *,
    url: str,
    title: str | None = None,
    publisher: str | None = None,
    published_at=None,
    kind: str | None = None,
) -> Source:
    """Return the existing source for this URL's content hash, or create one."""
    content_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:64]
    existing = await session.scalar(
        select(Source).where(Source.content_hash == content_hash)
    )
    if existing is not None:
        return existing
    source = Source(
        url=url,
        domain=urlparse(url).netloc,
        title=title,
        publisher=publisher,
        published_at=published_at,
        content_hash=content_hash,
        kind=kind,
    )
    session.add(source)
    await session.flush()
    return source


async def link_source(
    session: AsyncSession,
    event: Event,
    source: Source,
    *,
    relation: str = "reports",
    added_by: str | None = None,
    weights: SeverityWeights | None = None,
) -> bool:
    """Attach a source to an event (idempotent). Bumps source_count + refreshes scores.

    Returns True if a new link was created.
    """
    exists = await session.get(EventSource, (event.id, source.id))
    if exists is not None:
        return False
    session.add(
        EventSource(
            event_id=event.id, source_id=source.id, relation=relation, added_by=added_by
        )
    )
    event.source_count += 1
    sev, confidence = _derive_scores(event.source_count, weights)
    event.severity = sev.score
    event.severity_breakdown = {
        "impact": sev.impact,
        "social": sev.social,
        "corroboration": sev.corroboration,
    }
    event.confidence = confidence
    return True


async def get_or_create_entity(
    session: AsyncSession,
    *,
    kind: str,
    name: str,
    external_id: str | None = None,
    geo: GeoPoint | None = None,
) -> Entity:
    """Resolve an entity by ``(kind, external_id)`` when a QID is known, else by
    ``(kind, name_key)``; create it if absent. Caller commits."""
    name_key = entity_name_key(name)
    if external_id:
        existing = await session.scalar(
            select(Entity).where(Entity.kind == kind, Entity.external_id == external_id)
        )
        if existing is not None:
            return existing
    existing = await session.scalar(
        select(Entity).where(Entity.kind == kind, Entity.name_key == name_key)
    )
    if existing is not None:
        # Backfill a QID if we learned one since first sighting.
        if external_id and not existing.external_id:
            existing.external_id = external_id
        return existing
    entity = Entity(
        kind=kind,
        name=name.strip(),
        name_key=name_key,
        external_id=external_id,
        geom=_point_expr(geo),
    )
    session.add(entity)
    await session.flush()
    return entity


async def link_entity(
    session: AsyncSession,
    event: Event,
    entity: Entity,
    *,
    role: str = "subject",
    added_by: str | None = None,
) -> bool:
    """Tag an entity onto an event in a role (idempotent). Returns True if newly linked."""
    exists = await session.get(EventEntity, (event.id, entity.id, role))
    if exists is not None:
        return False
    session.add(
        EventEntity(event_id=event.id, entity_id=entity.id, role=role, added_by=added_by)
    )
    return True


async def link_relation(
    session: AsyncSession,
    *,
    src_event,
    dst_event,
    kind: str,
    weight: float = 1.0,
    created_by: str | None = None,
) -> bool:
    """Create a directed src→dst edge (idempotent per kind). If it exists, keep the
    stronger weight. Returns True if a new edge was created. No self-loops."""
    if src_event == dst_event:
        return False
    existing = await session.get(EventRelation, (src_event, dst_event, kind))
    if existing is not None:
        if weight > existing.weight:
            existing.weight = weight
        return False
    session.add(
        EventRelation(
            src_event=src_event,
            dst_event=dst_event,
            kind=kind,
            weight=weight,
            created_by=created_by,
        )
    )
    return True


async def link_event_media(
    session: AsyncSession,
    event_id,
    media: Media,
    *,
    role: str = "gallery",
    rank: int = 0,
    added_by: str | None = None,
) -> bool:
    """Attach a media item to an event (idempotent). Returns True if newly linked."""
    exists = await session.get(EventMedia, (event_id, media.id))
    if exists is not None:
        return False
    session.add(
        EventMedia(
            event_id=event_id, media_id=media.id, role=role, rank=rank, added_by=added_by
        )
    )
    return True


async def add_media_source(
    session: AsyncSession,
    media: Media,
    source_url: str,
    *,
    source_id=None,
    is_stable: bool = False,
) -> bool:
    """Record a host URL where this media was seen (idempotent). Returns True if new."""
    exists = await session.get(MediaSource, (media.id, source_url))
    if exists is not None:
        return False
    session.add(
        MediaSource(
            media_id=media.id, source_url=source_url, source_id=source_id, is_stable=is_stable
        )
    )
    return True


async def discover_media(
    session: AsyncSession,
    event: Event,
    *,
    url: str,
    kind: str,
    mime: str | None = None,
    role: str = "gallery",
    source_kind: str | None = None,
    source_id=None,
    added_by: str | None = None,
) -> Media:
    """Register a media URL found on an event and decide its archival disposition
    (ADR-0018). Dedups by ``source_url``; always links the event + records the host.

    Sensitive/hot/ephemeral media is queued for local capture (``pending``); durable,
    low-sensitivity media on a stable host is linked (``external``)."""
    domain = urlparse(url).netloc
    ephemerality = media_policy.origin_ephemerality(source_kind, domain)
    is_stable = ephemerality == "durable"

    existing = await session.scalar(select(Media).where(Media.source_url == url))
    if existing is not None:
        await link_event_media(session, event.id, existing, role=role, added_by=added_by)
        await add_media_source(session, existing, url, source_id=source_id, is_stable=is_stable)
        return existing

    sensitivity = media_policy.score_sensitivity(
        event.category, event.tags, source_kind=source_kind
    )
    disposition = media_policy.decide_disposition(
        sensitivity, ephemerality, stable_sources=1 if is_stable else 0
    )
    # link → reference the origin directly; pin/archive → queue for local capture.
    status = "external" if disposition == "link" else "pending"
    media = Media(
        kind=kind,
        source_url=url,
        embed_url=url if disposition == "link" else None,
        mime=mime,
        status=status,
        disposition=disposition,
        sensitivity=sensitivity,
        origin_kind=source_kind,
        added_by=added_by,
    )
    session.add(media)
    await session.flush()
    await link_event_media(session, event.id, media, role=role, added_by=added_by)
    await add_media_source(session, media, url, source_id=source_id, is_stable=is_stable)
    return media


async def apply_enrichment(
    session: AsyncSession,
    event: Event,
    result: EnrichmentResult,
    *,
    weights: SeverityWeights | None = None,
    agent: str = "enrich",
) -> None:
    """Apply LLM enrichment to an event: summary/category/tags, impact-aware severity,
    and the extracted deep-time references (sub-timeline). Caller commits."""
    event.summary = result.summary
    if result.category and not event.category:
        event.category = result.category
    if result.tags:
        event.tags = sorted(set(event.tags) | set(result.tags))

    # Recompute severity now that we have an impact signal (plus existing corroboration).
    sev = compute_severity(
        source_count=event.source_count, impact_raw=result.impact, weights=weights
    )
    event.severity = sev.score
    event.severity_breakdown = {
        "impact": sev.impact,
        "social": sev.social,
        "corroboration": sev.corroboration,
    }

    for ref in result.references:
        t_start, t_end = materialize_span(ref.year, ref.precision)
        session.add(
            EventReference(
                event_id=event.id,
                label=ref.label,
                t_start=t_start,
                t_end=t_end,
                subject_precision=ref.precision,
                detail=ref.detail,
                extracted_by=agent,
            )
        )

    # Tag extracted entities (people/orgs/places/topics) → the relation-linker anchors on
    # these. Unknown kinds/roles fall back to safe defaults so a loose LLM can't break us.
    for ent in result.entities:
        kind = ent.kind.strip().lower()
        if kind not in _ENTITY_KINDS:
            kind = "topic"
        role = ent.role.strip().lower()
        if role not in _ENTITY_ROLES:
            role = "subject"
        if not ent.name.strip():
            continue
        entity = await get_or_create_entity(session, kind=kind, name=ent.name)
        await link_entity(session, event, entity, role=role, added_by=agent)
