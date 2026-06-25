"""Smart causal relation linker (Tier-2 LLM) — the back-and-forth history chain.

This is the product's core differentiator: presenting, for an event, *what led to it* and *what
happened after* as a coherent, time-ordered story thread — not the everything-shares-a-country
noise of the co-occurrence backbone (chronos_agents.relate's same-place/same-actor edges).

Per anchor event (those not yet processed, most-severe first):
  1. **Candidates** — the K most semantically-similar events by pgvector cosine on the event
     ``embedding`` (so candidates are about the same real-world matter), excluding self.
  2. **LLM judgment** — one call lists the anchor + numbered candidates (title · year · summary)
     and asks, per candidate: is it genuinely part of the SAME real-world story/thread, and is it
     a *direct causal* link or merely *thematic*? With a 0-100 confidence.
  3. **Time-ordered edges** — for each related candidate at/above the confidence threshold, the
     earlier event is ``src`` and the later is ``dst`` (the graph convention: src=cause/earlier →
     dst=effect/later). Direct links use kind ``causal`` (they power ``/events/{id}/chain``);
     thematic ones use ``thematic`` (the related panel). Weight = confidence.

Every anchor is stamped ``events.chain_built_at`` so the agent converges through the backlog and
new events are picked up by the worker's maintenance heartbeat.
"""

from __future__ import annotations

import logging

from chronos_core import config_service, repository
from chronos_core.db import session_scope
from chronos_core.llm import build_router
from sqlalchemy import text

from chronos_agents._json import extract_json_object

log = logging.getLogger("chronos.agents.relate_smart")
AGENT = "relate-smart"

_SYSTEM = (
    "You connect world events into causal history threads. Given an ANCHOR event and a numbered "
    "list of CANDIDATE events, decide for EACH candidate whether it belongs to the SAME "
    "real-world story or causal thread as the anchor (e.g. the same conflict, deal, mission, "
    "scandal, disaster and its lead-up/aftermath) — NOT merely the same country or topic. "
    "Return ONLY JSON: {\"links\":[{\"i\":<candidate number>, \"related\":true/false, "
    "\"causal\":true/false, \"confidence\":0-100}]}. "
    "'related' = same story/thread. 'causal' = a direct cause→effect or precursor→sequel link "
    "(true) vs just thematically related background (false). Be strict: most candidates that only "
    "share a place or broad topic are related=false. Omit nothing; one entry per candidate."
)


def _event_line(n: int, title: str, year: float, summary: str | None) -> str:
    desc = (summary or "").strip().replace("\n", " ")[:240]
    return f"[{n}] ({year:.0f}) {title}" + (f" — {desc}" if desc else "")


async def _candidates(session, anchor_id, anchor_vec, limit: int, min_sim: float) -> list:
    """The K most embedding-similar published events to the anchor (cosine), excluding self."""
    rows = (
        await session.execute(
            text(
                "SELECT e.id, e.title, e.t_start, e.summary, "
                "       1 - (e.embedding <=> :vec) AS sim "
                "FROM events e "
                "WHERE e.status='published' AND e.embedding IS NOT NULL AND e.id <> :aid "
                "  AND (1 - (e.embedding <=> :vec)) >= :minsim "
                "ORDER BY e.embedding <=> :vec "
                "LIMIT :lim"
            ),
            {"vec": str(anchor_vec), "aid": anchor_id, "minsim": min_sim, "lim": limit},
        )
    ).all()
    return rows


async def _link_anchor(session, router, anchor, cfg) -> int:
    """Find + LLM-judge + write the smart chain edges for one anchor. Returns edges created."""
    cands = await _candidates(
        session, anchor.id, anchor.embedding, cfg["candidates"], cfg["min_sim"]
    )
    if not cands:
        return 0
    listing = "\n".join(
        _event_line(n + 1, c.title, c.t_start, c.summary) for n, c in enumerate(cands)
    )
    user = (
        f"ANCHOR: ({anchor.t_start:.0f}) {anchor.title}"
        + (f" — {(anchor.summary or '').strip()[:240]}" if anchor.summary else "")
        + f"\n\nCANDIDATES:\n{listing}"
    )
    try:
        resp = await router.complete(system=_SYSTEM, user=user, max_tokens=cfg["max_tokens"])
        data = extract_json_object(resp.text)
    except Exception:
        log.warning("relate_smart: LLM/parse failed for anchor %s", anchor.id, exc_info=True)
        return 0

    created = 0
    for item in data.get("links", []):
        try:
            idx = int(item.get("i", 0)) - 1
            conf = int(item.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        if not item.get("related") or conf < cfg["threshold"] or not (0 <= idx < len(cands)):
            continue
        cand = cands[idx]
        kind = "causal" if item.get("causal") else "thematic"
        # Time-ordered: earlier event is src (cause/lead-up), later is dst (effect/aftermath).
        if cand.t_start <= anchor.t_start:
            src, dst = cand.id, anchor.id
        else:
            src, dst = anchor.id, cand.id
        if await repository.link_relation(
            session, src_event=src, dst_event=dst, kind=kind,
            weight=conf / 100.0, created_by=AGENT,
        ):
            created += 1
    return created


async def run_smart_relate() -> dict:
    """LLM-build causal chain edges for a batch of un-processed events. Returns counts."""
    async with session_scope() as session:
        if not await config_service.get(session, "agents.relate_smart.enabled", True):
            return {"enabled": False}
        cfg = {
            "batch": int(await config_service.get(session, "agents.relate_smart.batch_size", 8)),
            "candidates": int(
                await config_service.get(session, "agents.relate_smart.candidates", 10)
            ),
            "min_sim": float(
                await config_service.get(session, "agents.relate_smart.min_similarity", 0.45)
            ),
            "threshold": int(
                await config_service.get(session, "agents.relate_smart.confidence_threshold", 70)
            ),
            "max_tokens": int(
                await config_service.get(session, "agents.relate_smart.max_tokens", 700)
            ),
        }
        rows = (
            await session.execute(
                text(
                    "SELECT id, title, t_start, summary, embedding FROM events "
                    "WHERE status='published' AND embedding IS NOT NULL "
                    "  AND summary IS NOT NULL AND chain_built_at IS NULL "
                    "ORDER BY severity DESC LIMIT :b"
                ),
                {"b": cfg["batch"]},
            )
        ).all()

        totals = {"anchors": len(rows), "edges": 0}
        router = await build_router(session)
        try:
            for anchor in rows:
                totals["edges"] += await _link_anchor(session, router, anchor, cfg)
                await session.execute(
                    text("UPDATE events SET chain_built_at = now() WHERE id = :id"),
                    {"id": anchor.id},
                )
                await session.commit()
        finally:
            await router.aclose()

    log.info("relate_smart: %s", totals)
    return totals
