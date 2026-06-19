"""Read queries for the entity-anchored history graph: search, entity listing, related
events, and the back-and-forth causal *chain* — the product's "dig through history" core.

Reuses the event projection helpers from chronos_api.queries so timeline/map/search/graph
all return the same ``EventRead`` shape.
"""

from __future__ import annotations

import uuid

from chronos_core.schemas.event import EventRead, GeoPoint
from chronos_core.schemas.graph import (
    ChainEdge,
    ChainResponse,
    EntityRead,
    EntityRole,
    RelatedEvent,
)
from chronos_core.schemas.media import MediaRead
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.queries import _EVENT_COLS, _event_read

# Causal kinds that form a *chain* (directed cause→effect). same-place/same-actor are mere
# co-occurrence and belong in the "related" panel, not the back/forth dig.
CHAIN_KINDS = ("precursor", "causal", "sequel")


def _entity_read(row) -> EntityRead:
    geo = GeoPoint(lon=row.lon, lat=row.lat) if row.lon is not None else None
    return EntityRead(
        id=row.id,
        kind=row.kind,
        name=row.name,
        external_id=row.external_id,
        geo=geo,
        event_count=getattr(row, "event_count", None),
    )


_ENTITY_COLS = """
    en.id, en.kind, en.name, en.external_id,
    CASE WHEN en.geom IS NOT NULL THEN ST_X(en.geom) END AS lon,
    CASE WHEN en.geom IS NOT NULL THEN ST_Y(en.geom) END AS lat
"""


# --- search ---------------------------------------------------------------------------


async def search_events(
    session: AsyncSession,
    *,
    q: str | None = None,
    t0: float | None = None,
    t1: float | None = None,
    category: str | None = None,
    limit: int = 50,
) -> list[EventRead]:
    """Find events by free text (title OR a linked entity name) within an optional time
    range. Backs the "search a location / event title / date" entry point."""
    clauses = ["e.status = 'published'"]
    params: dict = {"limit": limit}
    if q:
        clauses.append("(e.title ILIKE :qlike OR en.name ILIKE :qlike)")
        params["qlike"] = f"%{q}%"
    if t0 is not None:
        clauses.append("e.t_end >= :t0")
        params["t0"] = t0
    if t1 is not None:
        clauses.append("e.t_start <= :t1")
        params["t1"] = t1
    if category:
        clauses.append("e.category = :category")
        params["category"] = category
    where = " AND ".join(clauses)
    rows = (
        await session.execute(
            text(
                f"SELECT DISTINCT {_EVENT_COLS} FROM events e "
                "LEFT JOIN event_entities ee ON ee.event_id = e.id "
                "LEFT JOIN entities en ON en.id = ee.entity_id "
                f"WHERE {where} ORDER BY t_start LIMIT :limit"
            ),
            params,
        )
    ).all()
    return [_event_read(r) for r in rows]


async def search_entities(
    session: AsyncSession, *, q: str | None = None, kind: str | None = None, limit: int = 30
) -> list[EntityRead]:
    """Find entities (people/orgs/places/topics) by name, busiest first."""
    clauses = ["1 = 1"]
    params: dict = {"limit": limit}
    if q:
        clauses.append("en.name ILIKE :qlike")
        params["qlike"] = f"%{q}%"
    if kind:
        clauses.append("en.kind = :kind")
        params["kind"] = kind
    where = " AND ".join(clauses)
    rows = (
        await session.execute(
            text(
                f"SELECT {_ENTITY_COLS}, count(ee.event_id) AS event_count FROM entities en "
                "LEFT JOIN event_entities ee ON ee.entity_id = en.id "
                f"WHERE {where} GROUP BY en.id ORDER BY event_count DESC, en.name LIMIT :limit"
            ),
            params,
        )
    ).all()
    return [_entity_read(r) for r in rows]


async def events_for_entities(
    session: AsyncSession,
    entity_ids: list[uuid.UUID],
    *,
    t0: float | None = None,
    t1: float | None = None,
    limit: int = 200,
) -> list[EventRead]:
    """Events linked to **all** of the given entities, time-ordered. This is the
    "all events linking the US and Iran" query (intersection of entity tags)."""
    if not entity_ids:
        return []
    clauses = ["e.status = 'published'"]
    params: dict = {"ids": entity_ids, "n": len(set(entity_ids)), "limit": limit}
    if t0 is not None:
        clauses.append("e.t_end >= :t0")
        params["t0"] = t0
    if t1 is not None:
        clauses.append("e.t_start <= :t1")
        params["t1"] = t1
    where = " AND ".join(clauses)
    rows = (
        await session.execute(
            text(
                "WITH matched AS ("
                "  SELECT event_id FROM event_entities WHERE entity_id = ANY(:ids) "
                "  GROUP BY event_id HAVING count(DISTINCT entity_id) = :n"
                f") SELECT {_EVENT_COLS} FROM events e JOIN matched m ON m.event_id = e.id "
                f"WHERE {where} ORDER BY t_start LIMIT :limit"
            ),
            params,
        )
    ).all()
    return [_event_read(r) for r in rows]


# --- per-event graph views ------------------------------------------------------------


async def fetch_event_entities(
    session: AsyncSession, event_id: uuid.UUID
) -> list[EntityRole]:
    """The entities tagged on an event, with their roles."""
    rows = (
        await session.execute(
            text(
                f"SELECT {_ENTITY_COLS}, ee.role FROM event_entities ee "
                "JOIN entities en ON en.id = ee.entity_id "
                "WHERE ee.event_id = :id ORDER BY ee.role, en.name"
            ),
            {"id": event_id},
        )
    ).all()
    return [EntityRole(entity=_entity_read(r), role=r.role) for r in rows]


async def fetch_event_media(session: AsyncSession, event_id: uuid.UUID) -> list[MediaRead]:
    """Media attached to an event, ordered hero-first then by rank."""
    rows = (
        await session.execute(
            text(
                "SELECT m.id, m.kind, em.role, em.rank, m.storage_key, m.embed_url, "
                "m.thumbnail_key, m.mime, m.width, m.height, m.duration_s, m.caption, "
                "m.credit, m.license, m.status, m.disposition, m.sensitivity "
                "FROM event_media em JOIN media m ON m.id = em.media_id "
                "WHERE em.event_id = :id "
                "ORDER BY (em.role = 'hero') DESC, em.rank, m.created_at"
            ),
            {"id": event_id},
        )
    ).all()
    return [
        MediaRead(
            id=r.id, kind=r.kind, role=r.role, rank=r.rank, storage_key=r.storage_key,
            embed_url=r.embed_url, thumbnail_key=r.thumbnail_key, mime=r.mime,
            width=r.width, height=r.height, duration_s=r.duration_s, caption=r.caption,
            credit=r.credit, license=r.license, status=r.status,
            disposition=r.disposition, sensitivity=r.sensitivity,
            locally_stored=r.storage_key is not None and r.status == "stored",
        )
        for r in rows
    ]


async def fetch_related(
    session: AsyncSession, event_id: uuid.UUID, *, direction: str = "both", limit: int = 50
) -> list[RelatedEvent]:
    """One-hop neighbors of an event across **all** relation kinds (the "related" panel).

    direction: ``back`` = events that led to this · ``forward`` = events this led to ·
    ``both``.
    """
    out: list[RelatedEvent] = []
    if direction in ("back", "both"):
        rows = (
            await session.execute(
                text(
                    f"SELECT {_EVENT_COLS}, r.kind, r.weight FROM event_relations r "
                    "JOIN events e ON e.id = r.src_event "
                    "WHERE r.dst_event = :id AND e.status = 'published' "
                    "ORDER BY r.weight DESC LIMIT :limit"
                ),
                {"id": event_id, "limit": limit},
            )
        ).all()
        out += [
            RelatedEvent(event=_event_read(r), kind=r.kind, weight=r.weight, direction="back")
            for r in rows
        ]
    if direction in ("forward", "both"):
        rows = (
            await session.execute(
                text(
                    f"SELECT {_EVENT_COLS}, r.kind, r.weight FROM event_relations r "
                    "JOIN events e ON e.id = r.dst_event "
                    "WHERE r.src_event = :id AND e.status = 'published' "
                    "ORDER BY r.weight DESC LIMIT :limit"
                ),
                {"id": event_id, "limit": limit},
            )
        ).all()
        out += [
            RelatedEvent(event=_event_read(r), kind=r.kind, weight=r.weight, direction="forward")
            for r in rows
        ]
    return out


async def _chain_edges(
    session: AsyncSession, root: uuid.UUID, direction: str, depth: int
) -> list[ChainEdge]:
    """Recursively walk causal edges from ``root`` up to ``depth`` hops."""
    # ``back`` follows edges INTO the frontier (recurse on src); ``forward`` follows edges
    # OUT of it (recurse on dst). Only CHAIN_KINDS participate so the walk stays causal.
    if direction == "back":
        seed = "r.dst_event = :root"
        step = "r.dst_event = w.src_event"
    else:  # forward
        seed = "r.src_event = :root"
        step = "r.src_event = w.dst_event"
    sql = text(
        "WITH RECURSIVE walk(src_event, dst_event, kind, weight, depth) AS ("
        "  SELECT r.src_event, r.dst_event, r.kind, r.weight, 1 "
        "  FROM event_relations r "
        f"  WHERE {seed} AND r.kind = ANY(:kinds) "
        "  UNION "
        "  SELECT r.src_event, r.dst_event, r.kind, r.weight, w.depth + 1 "
        f"  FROM event_relations r JOIN walk w ON {step} "
        "  WHERE w.depth < :depth AND r.kind = ANY(:kinds)"
        ") SELECT DISTINCT src_event, dst_event, kind, weight FROM walk"
    )
    rows = (
        await session.execute(
            sql, {"root": root, "depth": depth, "kinds": list(CHAIN_KINDS)}
        )
    ).all()
    return [
        ChainEdge(src=r.src_event, dst=r.dst_event, kind=r.kind, weight=r.weight)
        for r in rows
    ]


async def fetch_chain(
    session: AsyncSession, root: uuid.UUID, *, direction: str = "both", depth: int = 2
) -> ChainResponse:
    """The causal chain around an event: nodes + edges reachable by following causal
    relations ``back`` (what led to it), ``forward`` (what it caused), or ``both``."""
    depth = max(1, min(depth, 4))
    edges: list[ChainEdge] = []
    if direction in ("back", "both"):
        edges += await _chain_edges(session, root, "back", depth)
    if direction in ("forward", "both"):
        edges += await _chain_edges(session, root, "forward", depth)

    # Dedup edges (back+forth can overlap) and collect every node id (incl. the root).
    seen: set[tuple] = set()
    deduped: list[ChainEdge] = []
    node_ids: set[uuid.UUID] = {root}
    for e in edges:
        key = (e.src, e.dst, e.kind)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
        node_ids |= {e.src, e.dst}

    nodes: list[EventRead] = []
    if node_ids:
        rows = (
            await session.execute(
                text(f"SELECT {_EVENT_COLS} FROM events e WHERE e.id = ANY(:ids) ORDER BY t_start"),
                {"ids": list(node_ids)},
            )
        ).all()
        nodes = [_event_read(r) for r in rows]
    return ChainResponse(
        root=root, direction=direction, depth=depth, nodes=nodes, edges=deduped
    )
