"""Interest profile — a decayed, weighted engagement count (ADR-0028, Phase-5 slice).

From the activity log (chronos_core.social_repo), build a profile of what a user engages
with: the **entities**, **categories**, **places**, and **sources/authors** attached to the
events they viewed/liked/commented/promoted, each weighted by the action weight and **decayed
exponentially** by age (config half-life). This is the cheap, no-ML substrate the For-You feed
matches against; the existing ``users.interest_vector`` column is reserved for a later
embedding pass.

Pure-ish: one read of the recent activity rows + a join to the touched events' entities,
categories, and sources. Everything else is in-memory aggregation, so the scoring is testable
without a database (see :func:`accumulate`).
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core import config_service
from chronos_core.models.social import ActivityLog
from chronos_core.schemas.social import InterestProfile

# How many recent activity rows to fold into a profile (bounded cost).
_MAX_ROWS = 500


@dataclass
class _Acc:
    """In-memory accumulators for one user's profile."""

    entities: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    categories: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    places: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    sources: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    n: int = 0


def decay_factor(age_days: float, half_life_days: float) -> float:
    """Exponential time-decay multiplier: 1.0 at age 0, 0.5 at one half-life."""
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (max(0.0, age_days) / half_life_days)


def accumulate(
    acc: _Acc,
    *,
    decayed_weight: float,
    category: str | None,
    entity_ids: list[str],
    place_ids: list[str],
    source_ids: list[str],
) -> None:
    """Fold one event's facets into the accumulators with a pre-decayed weight."""
    acc.n += 1
    if category:
        acc.categories[category] += decayed_weight
    for eid in entity_ids:
        acc.entities[eid] += decayed_weight
    for pid in place_ids:
        acc.places[pid] += decayed_weight
    for sid in source_ids:
        acc.sources[sid] += decayed_weight


def _top(d: dict[str, float], limit: int = 25) -> dict[str, float]:
    """The top-N entries by weight, rounded, descending."""
    items = sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return {k: round(v, 4) for k, v in items}


async def _half_life(session: AsyncSession) -> float:
    return float(await config_service.get(session, "rec.decay_half_life_days", 14.0))


async def compute_profile(
    session: AsyncSession, user_id: uuid.UUID, *, now: datetime | None = None
) -> InterestProfile:
    """Build the decayed interest profile for a user from their recent activity (ADR-0028)."""
    half_life = await _half_life(session)
    now = now or datetime.now(timezone.utc)

    rows = (
        await session.execute(
            select(ActivityLog.target_id, ActivityLog.weight, ActivityLog.created_at)
            .where(ActivityLog.user_id == user_id)
            .where(ActivityLog.target_type == "event")
            .order_by(ActivityLog.created_at.desc())
            .limit(_MAX_ROWS)
        )
    ).all()

    acc = _Acc()
    if not rows:
        return InterestProfile(sample_size=0)

    event_ids = [r[0] for r in rows]
    facets = await _event_facets(session, event_ids)

    for target_id, weight, created_at in rows:
        age_days = (now - _aware(created_at)).total_seconds() / 86400.0
        dw = float(weight) * decay_factor(age_days, half_life)
        cat, ents, places, srcs = facets.get(target_id, (None, [], [], []))
        accumulate(
            acc, decayed_weight=dw, category=cat,
            entity_ids=ents, place_ids=places, source_ids=srcs,
        )

    return InterestProfile(
        entities=_top(acc.entities),
        categories=_top(acc.categories),
        places=_top(acc.places),
        sources=_top(acc.sources),
        sample_size=acc.n,
    )


def _aware(dt: datetime) -> datetime:
    """Treat naive timestamps as UTC so the age math never raises."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _event_facets(
    session: AsyncSession, event_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[str | None, list[str], list[str], list[str]]]:
    """For a set of events, fetch (category, entity_ids, place_entity_ids, source_ids).

    One pass each over events / event_entities / event_sources, joined in Python. ``places``
    are the kind='place' subset of the tagged entities (the "where" facet)."""
    if not event_ids:
        return {}
    out: dict[uuid.UUID, tuple[str | None, list[str], list[str], list[str]]] = {
        eid: (None, [], [], []) for eid in event_ids
    }

    cat_rows = (
        await session.execute(
            text("SELECT id, category FROM events WHERE id = ANY(:ids)"),
            {"ids": event_ids},
        )
    ).all()
    cats = {r.id: r.category for r in cat_rows}

    ent_rows = (
        await session.execute(
            text(
                "SELECT ee.event_id, ee.entity_id, en.kind FROM event_entities ee "
                "JOIN entities en ON en.id = ee.entity_id WHERE ee.event_id = ANY(:ids)"
            ),
            {"ids": event_ids},
        )
    ).all()
    src_rows = (
        await session.execute(
            text("SELECT event_id, source_id FROM event_sources WHERE event_id = ANY(:ids)"),
            {"ids": event_ids},
        )
    ).all()

    ents: dict[uuid.UUID, list[str]] = defaultdict(list)
    places: dict[uuid.UUID, list[str]] = defaultdict(list)
    for r in ent_rows:
        ents[r.event_id].append(str(r.entity_id))
        if r.kind == "place":
            places[r.event_id].append(str(r.entity_id))
    srcs: dict[uuid.UUID, list[str]] = defaultdict(list)
    for r in src_rows:
        srcs[r.event_id].append(str(r.source_id))

    for eid in event_ids:
        out[eid] = (cats.get(eid), ents.get(eid, []), places.get(eid, []), srcs.get(eid, []))
    return out
