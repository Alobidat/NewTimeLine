"""Publisher: write a CandidateEvent to the canonical store (Tier-1, no LLM).

Phase-1 dedup is simple: if the candidate's source URL is already attached to an event,
we skip (the article is already represented). Embedding-based dedup arrives in Phase 3
(docs/ai-agents.md §2.3). Write logic itself is shared via chronos_core.repository.
"""

from __future__ import annotations

from chronos_core import config_service, repository
from chronos_core.domain.severity import SeverityWeights
from chronos_core.models.event import Event
from chronos_core.models.source import EventSource
from chronos_core.schemas.event import EventCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_agents.normalize import CandidateEvent


async def load_weights(session: AsyncSession) -> SeverityWeights:
    """Severity weights from the Config Service (falls back to defaults)."""
    return SeverityWeights.from_config(await config_service.get(session, "severity.weights"))


async def publish_candidate(
    session: AsyncSession,
    cand: CandidateEvent,
    *,
    agent_name: str,
    weights: SeverityWeights | None = None,
) -> Event | None:
    """Create an event for the candidate + attach its source. Returns None if a duplicate."""
    source = await repository.get_or_create_source(
        session,
        url=cand.source_url,
        title=cand.source_title,
        publisher=cand.source_publisher,
        published_at=cand.source_published_at,
        kind=cand.source_kind,
    )
    # Dedup: source already linked to an event → already represented.
    already_linked = await session.scalar(
        select(EventSource.event_id).where(EventSource.source_id == source.id).limit(1)
    )
    if already_linked is not None:
        return None

    event = await repository.create_event(
        session,
        EventCreate(
            title=cand.title,
            summary=cand.summary,
            t_start=cand.t_start,
            t_end=cand.t_end,
            time_precision=cand.time_precision,
            instant=cand.instant,
            category=cand.category,
            tags=cand.tags,
            geo=cand.geo,
            geo_label=None,
            created_by_agent=agent_name,
        ),
        weights=weights,
    )
    await repository.link_source(session, event, source, added_by=agent_name, weights=weights)
    return event
