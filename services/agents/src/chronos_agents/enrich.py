"""Tier-2 enricher: add AI summaries, categories, tags, impact, and deep-time references
to events that lack them. Provider-agnostic + budget-aware via chronos_core.llm (the router
auto-switches to a local LLM when the cloud budget is spent — ADR-0015).

Grounding note (Phase 3a): we prompt on the event's own fields. Fetching/citing full source
text (object-store snapshots) is a later enrichment-quality improvement.
"""

from __future__ import annotations

import json
import logging

from chronos_core import config_service, repository
from chronos_core.db import session_scope
from chronos_core.llm import build_router
from chronos_core.llm.router import LLMRouter
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.schemas.enrichment import EnrichmentResult
from sqlalchemy import select

from chronos_agents.publish import load_weights

log = logging.getLogger("chronos.agents.enrich")
AGENT = "enrich"

_SYSTEM = (
    "You enrich world-event records. Return ONLY a JSON object, no prose, no code fences. "
    "Be neutral and source-grounded; never invent facts. Schema: "
    '{"summary": string (1-3 sentences), "category": string|null, "tags": string[], '
    '"impact": number (rough magnitude proxy, 0 if unknown), '
    '"references": [{"label": string, "year": number (signed; negative=BC), '
    '"precision": "exact|day|month|year|decade|century|era", "detail": string|null}]}. '
    "references are deep-history subjects the event discusses (empty if none)."
)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response (tolerates fences/extra prose)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])


def _user_prompt(event: Event) -> str:
    parts = [f"Title: {event.title}"]
    if event.category:
        parts.append(f"Current category: {event.category}")
    if event.tags:
        parts.append(f"Current tags: {', '.join(event.tags)}")
    if event.geo_label:
        parts.append(f"Place: {event.geo_label}")
    parts.append(f"Approximate year: {event.t_start:.0f}")
    return "\n".join(parts)


async def _enrich_one(session, router: LLMRouter, event: Event, weights, max_tokens: int) -> bool:
    resp = await router.complete(
        system=_SYSTEM, user=_user_prompt(event), max_tokens=max_tokens
    )
    try:
        result = EnrichmentResult.model_validate(_extract_json(resp.text))
    except Exception:
        log.warning("unparseable enrichment for event %s (provider=%s)", event.id, resp.provider)
        return False
    await repository.apply_enrichment(session, event, result, weights=weights, agent=AGENT)
    return True


async def enrich_pending() -> dict:
    """Enrich a batch of events that have no summary yet. Returns a summary of counts."""
    async with session_scope() as session:
        if not await config_service.get(session, "agents.enrich.enabled", True):
            log.info("enrich disabled via config")
            return {"enabled": False}
        batch = int(await config_service.get(session, "agents.enrich.batch_size", 20))
        max_tokens = int(await config_service.get(session, "agents.enrich.max_tokens", 800))
        weights = await load_weights(session)
        router = await build_router(session)

        rows = (
            await session.execute(
                select(Event)
                .where(Event.summary.is_(None), Event.status == EventStatus.PUBLISHED)
                .order_by(Event.severity.desc())
                .limit(batch)
            )
        ).scalars().all()

        totals = {"candidates": len(rows), "enriched": 0, "failed": 0}
        try:
            for event in rows:
                ok = await _enrich_one(session, router, event, weights, max_tokens)
                totals["enriched" if ok else "failed"] += 1
        finally:
            await router.aclose()

    log.info("enrich: %s", totals)
    return totals
