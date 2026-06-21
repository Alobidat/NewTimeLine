"""Geocoder (Phase 3b): resolve geo_label → PostGIS geometry for events, and name → geom
for place entities, via Nominatim (OpenStreetMap).

Strategy (structured-first):
  1. Events with geo_label set but geom NULL — look up the label.
  2. Entities of kind='place' with geom NULL — look up the entity name.

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

from chronos_core import config_service
from chronos_core.db import session_scope
from chronos_core.models.entity import Entity
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event

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


async def _geocode_events(
    session: AsyncSession,
    client: httpx.AsyncClient,
    batch_size: int,
) -> tuple[int, int]:
    """Geocode events where geo_label is set but geom is NULL. Returns (geocoded, failed)."""
    rows = (
        await session.execute(
            select(Event.id, Event.geo_label)
            .where(Event.geom.is_(None))
            .where(Event.geo_label.isnot(None))
            .where(Event.status == EventStatus.PUBLISHED)
            .limit(batch_size)
        )
    ).all()

    geocoded = failed = 0
    for (event_id, geo_label) in rows:
        await asyncio.sleep(_RATE_DELAY)
        coords = await _lookup(client, geo_label)
        if coords is None:
            log.debug("event %s: no result for %r", event_id, geo_label)
            failed += 1
            continue
        lat, lon = coords
        await session.execute(
            update(Event)
            .where(Event.id == event_id)
            .values(geom=_point_expr(lat, lon))
        )
        log.info("event %s: geocoded %r → (%.4f, %.4f)", event_id, geo_label, lat, lon)
        geocoded += 1

    return geocoded, failed


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
            keys=["agents.geocode.enabled", "agents.geocode.batch_size"],
        )

    enabled: bool = cfg.get("agents.geocode.enabled", True)
    if not enabled:
        log.info("geocoder disabled — skipping")
        return {"candidates": 0, "geocoded": 0, "failed": 0, "skipped": 0}

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
            ev_geo, ev_fail = await _geocode_events(session, client, event_batch)
            en_geo, en_fail = await _geocode_entities(session, client, entity_batch)
            await session.commit()

    total_geo = ev_geo + en_geo
    total_fail = ev_fail + en_fail
    log.info(
        "geocode run done: geocoded=%d failed=%d (events=%d/%d entities=%d/%d)",
        total_geo, total_fail, ev_geo, ev_fail, en_geo, en_fail,
    )
    return {
        "candidates": ev_geo + ev_fail + en_geo + en_fail,
        "geocoded": total_geo,
        "failed": total_fail,
    }
