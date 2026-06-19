"""Relation-linker (Tier-1, no LLM): build the directed history graph from shared entities.

The product's core promise is digging back-and-forth from an event through what *led to*
it and what it *caused*, anchored on places/actors (the "US ↔ Iran" example). This agent
provides the cheap **co-occurrence** backbone — the "related events" panel:

For each event in the batch, find other published events that share ≥ ``min_shared``
entities and connect them. Direction follows time (earlier = ``src`` → later = ``dst``).
Edge ``kind``:
- ``same-place``  when a shared entity is a place,
- ``same-actor``  when a shared entity is a person/org.

It deliberately does **not** infer ``causal``/``precursor`` edges from shared entities: when
ubiquitous anchors (US + Iran) sit on every event, that links everything to everything. The
causal **chain** (``/events/{id}/chain``) is built only from genuine cause→effect links —
curated, or extracted by the LLM enricher / Tier-3 dig. Weight comes from
:func:`chronos_core.domain.entities.relation_weight`; edges are written idempotently.
"""

from __future__ import annotations

import logging

from chronos_core import config_service, repository
from chronos_core.db import session_scope
from chronos_core.domain.entities import relation_weight
from sqlalchemy import text

log = logging.getLogger("chronos.agents.relate")
AGENT = "relate"

# Events recently touched (enriched/created), restricted to those that actually have
# entities — without entities there is nothing to anchor a link on.
_BATCH_SQL = text(
    "SELECT e.id, e.t_start FROM events e "
    "WHERE e.status = 'published' "
    "AND EXISTS (SELECT 1 FROM event_entities ee WHERE ee.event_id = e.id) "
    "ORDER BY e.updated_at DESC LIMIT :batch"
)

# Neighbors of one event: other published events sharing ≥ :min_shared entities, with
# flags for whether the shared set includes a place / an actor.
_NEIGHBORS_SQL = text(
    "SELECT ee2.event_id AS other_id, e2.t_start AS other_t, count(*) AS shared, "
    "bool_or(en.kind = 'place') AS shares_place, "
    "bool_or(en.kind IN ('person', 'org')) AS shares_actor "
    "FROM event_entities ee1 "
    "JOIN event_entities ee2 ON ee2.entity_id = ee1.entity_id AND ee2.event_id <> ee1.event_id "
    "JOIN entities en ON en.id = ee1.entity_id "
    "JOIN events e2 ON e2.id = ee2.event_id AND e2.status = 'published' "
    "WHERE ee1.event_id = :eid "
    "GROUP BY ee2.event_id, e2.t_start "
    "HAVING count(*) >= :min_shared "
    "LIMIT :max_neighbors"
)


def _edge_kinds(shares_place: bool, shares_actor: bool) -> list[str]:
    """Which relation kinds this overlap justifies.

    Only **co-occurrence** edges (same-place / same-actor) — these power the "related events"
    panel. We deliberately do NOT infer ``precursor``/``causal`` edges from mere shared
    entities: when ubiquitous anchors (e.g. US + Iran) sit on every event, that would link
    everything to everything. The causal **chain** is built from genuine cause→effect links
    (curated, or LLM-extracted by the enricher/Tier-3) — see chronos_api ``/events/{id}/chain``.
    """
    kinds: list[str] = []
    if shares_place:
        kinds.append("same-place")
    if shares_actor:
        kinds.append("same-actor")
    return kinds


async def link_relations() -> dict:
    """Link a batch of recently-touched events into the history graph. Returns counts."""
    async with session_scope() as session:
        if not await config_service.get(session, "agents.relate.enabled", True):
            log.info("relate disabled via config")
            return {"enabled": False}
        batch = int(await config_service.get(session, "agents.relate.batch_size", 50))
        min_shared = int(await config_service.get(session, "agents.relate.min_shared", 1))
        max_neighbors = int(await config_service.get(session, "agents.relate.max_neighbors", 200))

        events = (await session.execute(_BATCH_SQL, {"batch": batch})).all()
        totals = {"candidates": len(events), "edges": 0}

        for ev in events:
            neighbors = (
                await session.execute(
                    _NEIGHBORS_SQL,
                    {"eid": ev.id, "min_shared": min_shared, "max_neighbors": max_neighbors},
                )
            ).all()
            for nb in neighbors:
                # Orient by time: earlier event is the cause (src), later is the effect (dst).
                if ev.t_start <= nb.other_t:
                    src, dst = ev.id, nb.other_id
                else:
                    src, dst = nb.other_id, ev.id
                weight = relation_weight(nb.shared, shares_location=bool(nb.shares_place))
                for kind in _edge_kinds(bool(nb.shares_place), bool(nb.shares_actor)):
                    created = await repository.link_relation(
                        session, src_event=src, dst_event=dst,
                        kind=kind, weight=weight, created_by=AGENT,
                    )
                    if created:
                        totals["edges"] += 1

    log.info("relate: %s", totals)
    return totals
