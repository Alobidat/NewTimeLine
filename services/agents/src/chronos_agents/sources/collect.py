"""On-demand collection agent (event-presentation.md §5.2 / §6).

``run_collect(subject)`` queries every **enabled** source adapter for a subject and runs the
candidates through the normal ``publish.publish_candidate`` path (→ enrich → relate → geocode →
media downstream). Media-rich, clip-bearing adapters are queried **first** (clips-first,
ADR-0023) so the most-presentable events arrive first and stream to the client soonest.

Phase C enqueues ``collect`` jobs onto the Redis run-queue; this agent handles them. The
subject comes from the job's args, so ``run_collect`` accepts ``SubjectQuery`` fields directly.
"""

from __future__ import annotations

import logging

from chronos_core import config_service
from chronos_core.db import session_scope

from chronos_agents.publish import load_weights, publish_candidate
from chronos_agents.sources import registry
from chronos_agents.sources.base import SourceAdapter, SubjectQuery

log = logging.getLogger("chronos.agents.collect")
AGENT = "collect"


def _adapter_priority(a: SourceAdapter) -> tuple[int, int]:
    """Sort key: clip-bearing first, then media-rich (lower tuple sorts earlier)."""
    caps = a.capabilities
    return (0 if caps.yields_clips else 1, 0 if caps.media_rich else 1)


async def run_collect(subject: SubjectQuery) -> dict:
    """Collect events for ``subject`` from all enabled adapters and publish them.

    Returns counts: adapters queried, candidates collected, published, skipped (duplicates)."""
    totals = {
        "subject": subject.text(), "adapters": 0,
        "collected": 0, "published": 0, "skipped": 0,
    }
    if subject.is_empty():
        log.info("collect: empty subject — nothing to do")
        return totals

    async with session_scope() as session:
        if not await config_service.get(session, "agents.collect.enabled", True):
            log.info("collect disabled via config")
            return {**totals, "enabled": False}
        max_per_adapter = int(
            await config_service.get(session, "agents.collect.max_per_adapter", 10)
        )
        adapters = await registry.enabled_adapters(session)
        weights = await load_weights(session)

    # Clips-first ordering so media-rich events publish (and stream) before text-heavy ones.
    adapters = [a for a in adapters if a.can_handle(subject)]
    adapters.sort(key=_adapter_priority)
    totals["adapters"] = len(adapters)

    for adapter in adapters:
        try:
            candidates = await adapter.collect(subject, limit=max_per_adapter)
        except Exception:
            log.exception("collect: adapter %s failed", adapter.id)
            continue
        totals["collected"] += len(candidates)
        # Each candidate in its own short transaction so one bad write can't lose the rest.
        for cand in candidates:
            try:
                async with session_scope() as session:
                    event = await publish_candidate(
                        session, cand, agent_name=AGENT, weights=weights
                    )
            except Exception:
                log.exception("collect: publish failed for %r", cand.source_url)
                continue
            totals["published" if event is not None else "skipped"] += 1
        log.info("collect: adapter %s → %d candidates", adapter.id, len(candidates))

    log.info("collect done: %s", totals)
    return totals
