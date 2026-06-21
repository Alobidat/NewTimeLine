"""Geocoder (Phase 3b + 3c cascade): resolve a location for *every* event (ADR-0020), and
name → geom for place entities, via Nominatim (OpenStreetMap) + curated fallbacks.

Per-event **resolution cascade** (stop at the first hit):
  1. geom already set — skip.
  2. ``geo_label`` → Nominatim lookup (network).
  3. existing ``location``/``actor`` **place entities** that already have a geom.
  4. **text analysis** — country names/demonyms in title+summary+body → centroid (no network).
  5. **last resort** — the **news-agency / source** country (domain → country → centroid).
An event still unresolved after all five is left geom-NULL and counted as ``unresolved`` so
the data-integrity check can flag it (it is held back from the map, never shown broken).

Place entities (kind='place', geom NULL) are still geocoded by name via Nominatim.

Nominatim usage policy requires a descriptive User-Agent and ≤1 req/s. We throttle with
a configurable delay (default 1.1 s) so batch runs stay compliant out of the box.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core import config_service, repository
from chronos_core.db import session_scope
from chronos_core.domain import location
from chronos_core.models.entity import Entity, EventEntity
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.models.source import EventSource, Source
from chronos_core.schemas.event import GeoPoint

log = logging.getLogger("chronos.agents.geocode")
AGENT = "geocode"

_USER_AGENT = "Chronos/1.0 NewTimeLine geocoder (github.com/newtimeline)"
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Seconds between Nominatim requests (policy: ≤1 req/s).
_RATE_DELAY = 1.1


async def _lookup(client: httpx.AsyncClient, query: str) -> tuple[float, float] | None:
    """Return (lat, lon) for a place name, or None if not found / error."""
    try:
        resp = await client.get(
            _NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": "1"},
        )
        resp.raise_for_status()
        results: list[dict[str, Any]] = resp.json()
        if not results:
            return None
        r = results[0]
        return float(r["lat"]), float(r["lon"])
    except Exception:
        log.exception("Nominatim lookup failed for %r", query)
        return None


def _point_expr(lat: float, lon: float):
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)


async def _set_event_geom(session: AsyncSession, event_id, lat: float, lon: float) -> None:
    await session.execute(
        update(Event).where(Event.id == event_id).values(geom=_point_expr(lat, lon))
    )


async def _existing_location_point(
    session: AsyncSession, event_id
) -> tuple[float, float] | None:
    """Cascade step 3: a (lat, lon) from an already-geocoded location/actor place entity."""
    row = (
        await session.execute(
            select(func.ST_Y(Entity.geom), func.ST_X(Entity.geom))
            .select_from(EventEntity)
            .join(Entity, Entity.id == EventEntity.entity_id)
            .where(EventEntity.event_id == event_id)
            .where(EventEntity.role.in_(["location", "actor"]))
            .where(Entity.kind == "place")
            .where(Entity.geom.isnot(None))
            .limit(1)
        )
    ).first()
    return (float(row[0]), float(row[1])) if row else None


async def _attach_countries(
    session: AsyncSession, event_id, countries: list[str], *, method: str
) -> tuple[float, float] | None:
    """Create/link place entities (role=location) for each country with its centroid; return
    the primary (first) centroid so it can become the event's geom. Records ``method`` in
    ``added_by`` for audit (e.g. 'geocode:text', 'geocode:agency')."""
    primary: tuple[float, float] | None = None
    event = await session.get(Event, event_id)
    for name in countries:
        pt = location.centroid(name)
        if pt is None:
            continue
        lat, lon = pt
        entity = await repository.get_or_create_entity(
            session, kind="place", name=name, geo=GeoPoint(lon=lon, lat=lat)
        )
        await repository.link_entity(
            session, event, entity, role="location", added_by=f"{AGENT}:{method}"
        )
        if primary is None:
            primary = pt
    return primary


async def _source_country_point(
    session: AsyncSession, event_id
) -> tuple[str, tuple[float, float]] | None:
    """Cascade step 5: the news-agency country from the event's source domains."""
    domains = (
        await session.execute(
            select(Source.domain)
            .select_from(EventSource)
            .join(Source, Source.id == EventSource.source_id)
            .where(EventSource.event_id == event_id)
        )
    ).scalars().all()
    for domain in domains:
        country = location.domain_country(domain)
        if country is None:
            continue
        pt = location.centroid(country)
        if pt is not None:
            return country, pt
    return None


async def _resolve_one(
    session: AsyncSession,
    client: httpx.AsyncClient,
    *,
    use_cascade: bool,
    agency_fallback: bool,
    event_id,
    geo_label: str | None,
    title: str,
    summary: str | None,
    body: str | None,
) -> str:
    """Run the cascade for one event. Returns the method that resolved it, or 'unresolved'."""
    # Step 2 — geo_label via Nominatim.
    if geo_label:
        await asyncio.sleep(_RATE_DELAY)
        coords = await _lookup(client, geo_label)
        if coords is not None:
            await _set_event_geom(session, event_id, *coords)
            return "geo_label"

    if not use_cascade:
        return "unresolved"

    # Step 3 — existing location/actor place entities.
    pt = await _existing_location_point(session, event_id)
    if pt is not None:
        await _set_event_geom(session, event_id, *pt)
        return "entity"

    # Step 4 — text analysis of title/summary/body.
    countries = location.extract_countries(title, summary, body, geo_label)
    if countries:
        primary = await _attach_countries(session, event_id, countries, method="text")
        if primary is not None:
            await _set_event_geom(session, event_id, *primary)
            return "text"

    # Step 5 — last resort: news-agency country.
    if agency_fallback:
        agency = await _source_country_point(session, event_id)
        if agency is not None:
            country, pt = agency
            await _attach_countries(session, event_id, [country], method="agency")
            await _set_event_geom(session, event_id, *pt)
            return "agency"

    return "unresolved"


async def _geocode_events(
    session: AsyncSession,
    client: httpx.AsyncClient,
    batch_size: int,
    *,
    use_cascade: bool,
    agency_fallback: bool,
) -> dict[str, int]:
    """Resolve a location for events with geom NULL via the cascade (ADR-0020).

    Returns per-method counts: geo_label / entity / text / agency / unresolved.
    Events with a geo_label are processed first so the precise Nominatim path runs while the
    rate-limited budget lasts; cascade-only events (no label) cost no network time."""
    rows = (
        await session.execute(
            select(Event.id, Event.geo_label, Event.title, Event.summary, Event.body)
            .where(Event.geom.is_(None))
            .where(Event.status == EventStatus.PUBLISHED)
            .order_by(Event.geo_label.is_(None))  # labelled events first
            .limit(batch_size)
        )
    ).all()

    counts = {"geo_label": 0, "entity": 0, "text": 0, "agency": 0, "unresolved": 0}
    for (event_id, geo_label, title, summary, body) in rows:
        method = await _resolve_one(
            session,
            client,
            use_cascade=use_cascade,
            agency_fallback=agency_fallback,
            event_id=event_id,
            geo_label=geo_label,
            title=title,
            summary=summary,
            body=body,
        )
        counts[method] += 1
        log.info("event %s: location via %s", event_id, method)
    return counts


async def _geocode_entities(
    session: AsyncSession,
    client: httpx.AsyncClient,
    batch_size: int,
) -> tuple[int, int]:
    """Geocode place entities that lack a geom. Returns (geocoded, failed)."""
    rows = (
        await session.execute(
            select(Entity.id, Entity.name)
            .where(Entity.kind == "place")
            .where(Entity.geom.is_(None))
            .limit(batch_size)
        )
    ).all()

    geocoded = failed = 0
    for (entity_id, name) in rows:
        await asyncio.sleep(_RATE_DELAY)
        coords = await _lookup(client, name)
        if coords is None:
            log.debug("entity %s: no result for %r", entity_id, name)
            failed += 1
            continue
        lat, lon = coords
        await session.execute(
            update(Entity)
            .where(Entity.id == entity_id)
            .values(geom=_point_expr(lat, lon))
        )
        log.info("entity %s: geocoded %r → (%.4f, %.4f)", entity_id, name, lat, lon)
        geocoded += 1

    return geocoded, failed


async def run_geocode() -> dict[str, int]:
    """Main entry point: geocode a batch of events + place entities."""
    async with session_scope() as session:
        cfg = await config_service.get_many(
            session,
            keys=[
                "agents.geocode.enabled",
                "agents.geocode.batch_size",
                "agents.geocode.cascade",
                "agents.geocode.agency_fallback",
            ],
        )

    enabled: bool = cfg.get("agents.geocode.enabled", True)
    if not enabled:
        log.info("geocoder disabled — skipping")
        return {"candidates": 0, "geocoded": 0, "failed": 0, "skipped": 0}

    use_cascade: bool = cfg.get("agents.geocode.cascade", True)
    agency_fallback: bool = cfg.get("agents.geocode.agency_fallback", True)
    batch_size: int = int(cfg.get("agents.geocode.batch_size", 20))
    # Split budget evenly: half for events, half for entities (at least 1 each).
    event_batch = max(1, batch_size // 2)
    entity_batch = max(1, batch_size - event_batch)

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=15,
        follow_redirects=True,
    ) as client:
        async with session_scope() as session:
            counts = await _geocode_events(
                session,
                client,
                event_batch,
                use_cascade=use_cascade,
                agency_fallback=agency_fallback,
            )
            en_geo, en_fail = await _geocode_entities(session, client, entity_batch)
            await session.commit()

    ev_geo = counts["geo_label"] + counts["entity"] + counts["text"] + counts["agency"]
    total_geo = ev_geo + en_geo
    total_fail = counts["unresolved"] + en_fail
    log.info(
        "geocode run done: geocoded=%d unresolved=%d "
        "(events: label=%d entity=%d text=%d agency=%d unresolved=%d; entities=%d/%d)",
        total_geo, total_fail,
        counts["geo_label"], counts["entity"], counts["text"], counts["agency"],
        counts["unresolved"], en_geo, en_fail,
    )
    return {
        "candidates": ev_geo + counts["unresolved"] + en_geo + en_fail,
        "geocoded": total_geo,
        "failed": total_fail,
        **{f"by_{k}": v for k, v in counts.items()},
    }
