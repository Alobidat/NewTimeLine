"""Source-validation aggregation (Phase 4 trust layer).

Turns reputation-weighted source votes into a source ``quality_score`` and an event
``confidence``, and awards a little reputation for participating. Called synchronously by the
source-vote endpoint so a verdict updates trust immediately. The math is in
``chronos_core.domain.validation``; this module only gathers + writes.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.domain import validation

# A voter's reputation weight, in SQL — mirrors validation.vote_weight (1 + ln(1+rep)).
_WEIGHT = "(1.0 + ln(1 + greatest(u.reputation, 0)))"


async def _weighted_verdicts(
    session: AsyncSession, where: str, params: dict
) -> tuple[float, float, float]:
    """Reputation-weighted (corroborate, dispute, irrelevant) sums for a vote subset."""
    rows = (
        await session.execute(
            text(
                f"SELECT sv.verdict, sum({_WEIGHT}) AS w FROM source_votes sv "
                f"JOIN users u ON u.id = sv.user_id WHERE {where} GROUP BY sv.verdict"
            ),
            params,
        )
    ).all()
    by = {r.verdict: float(r.w or 0.0) for r in rows}
    return by.get("corroborate", 0.0), by.get("dispute", 0.0), by.get("irrelevant", 0.0)


async def recompute_source_quality(session: AsyncSession, source_id: uuid.UUID) -> int:
    """Recompute + store a source's ``quality_score`` from all its votes (across events)."""
    c, d, i = await _weighted_verdicts(
        session, "sv.source_id = :sid", {"sid": source_id}
    )
    score = validation.source_quality(c, d, i)
    await session.execute(
        text("UPDATE sources SET quality_score = :q WHERE id = :sid"),
        {"q": score, "sid": source_id},
    )
    return score


async def recompute_event_confidence(session: AsyncSession, event_id: uuid.UUID) -> int:
    """Recompute + store an event's ``confidence`` from its source count, the quality of its
    sources, and the net verdict cast on this event."""
    source_count = int(
        await session.scalar(
            text("SELECT source_count FROM events WHERE id = :eid"), {"eid": event_id}
        )
        or 0
    )
    avg_quality = float(
        await session.scalar(
            text(
                "SELECT avg(s.quality_score) FROM event_sources es "
                "JOIN sources s ON s.id = es.source_id WHERE es.event_id = :eid"
            ),
            {"eid": event_id},
        )
        or 50.0
    )
    c, d, _i = await _weighted_verdicts(
        session, "sv.event_id = :eid", {"eid": event_id}
    )
    conf = validation.blended_confidence(source_count, avg_quality, c, d)
    await session.execute(
        text("UPDATE events SET confidence = :c WHERE id = :eid"),
        {"c": conf, "eid": event_id},
    )
    return conf


async def award_reputation(
    session: AsyncSession, user_id: uuid.UUID, points: int = validation.VOTE_REPUTATION
) -> None:
    """Add reputation to a user for a constructive contribution (best-effort, caller commits)."""
    await session.execute(
        text("UPDATE users SET reputation = reputation + :p WHERE id = :uid"),
        {"p": points, "uid": user_id},
    )
