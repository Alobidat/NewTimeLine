"""Deduper (Phase 3b): fill event embeddings via pgvector, then merge near-duplicates.

Two-phase per run:
  1. Embed — find events whose ``embedding`` column is NULL; batch-call the configured
     OpenAI-compatible /embeddings endpoint; store the resulting vectors.
  2. Dedup — for each newly-embedded event, ask pgvector for the top-K most similar
     neighbours within a configurable time window; if cosine similarity ≥ threshold,
     mark the newer event MERGED into the older canonical one.

The similarity threshold defaults to 0.95 (very conservative) so we only auto-merge
events that are clearly the same story — not merely related. Operators can tune this
via the Admin Portal (``agents.dedup.similarity_threshold``).
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core import config_service
from chronos_core.db import session_scope
from chronos_core.llm.embedder import build_embedder
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import EMBEDDING_DIM, Event

log = logging.getLogger("chronos.agents.dedup")
AGENT = "dedup"

# Top-K candidates fetched per event for similarity comparison.
_TOP_K = 5


def _embed_text(event: Event) -> str:
    """Build the text string to embed for an event."""
    parts = [event.title]
    if event.summary:
        parts.append(event.summary)
    if event.category:
        parts.append(event.category)
    return ". ".join(parts)


# Embed in small sub-chunks so one bad/oversized input can't 400 the whole batch (some
# OpenAI-compatible /embeddings servers reject a large multi-input call or an empty string).
_EMBED_CHUNK = 8


async def _embed_batch(
    session: AsyncSession,
    events: list[Event],
    embedder,
) -> int:
    """Compute and store embeddings for a batch of events. Returns count stored. Resilient: a
    failing sub-chunk is skipped (logged) rather than dropping the whole batch."""
    stored = 0
    for start in range(0, len(events), _EMBED_CHUNK):
        chunk = events[start : start + _EMBED_CHUNK]
        # Never send an empty string (a 400 trigger on some servers) — fall back to the title;
        # and cap length so an over-long event can't exceed the embedding model's context (~512
        # tokens) and 400 the request.
        texts = [(_embed_text(e) or e.title or "event")[:1500] for e in chunk]
        try:
            vectors = await embedder.embed(texts)
        except Exception:
            log.warning("embedding sub-chunk of %d failed; skipping", len(chunk), exc_info=True)
            continue
        if len(vectors) != len(chunk):
            log.warning("embedder returned %d vectors for %d events", len(vectors), len(chunk))
            continue
        for event, vec in zip(chunk, vectors):
            if len(vec) != EMBEDDING_DIM:
                log.warning(
                    "event %s: got %d-dim vector, expected %d (check llm.embedding.model)",
                    event.id, len(vec), EMBEDDING_DIM,
                )
                continue
            event.embedding = vec
            stored += 1
    return stored


async def _dedup_event(
    session: AsyncSession,
    event: Event,
    threshold: float,
    time_window: float,
) -> int:
    """Find and merge near-duplicates of one (just-embedded) event. Returns merged count."""
    if event.embedding is None:
        return 0

    # pgvector cosine distance: smaller = more similar. (1 - distance) = similarity.
    # We cast the Python list to a Postgres vector literal via the ::vector cast.
    vec_literal = "[" + ",".join(str(x) for x in event.embedding) + "]"

    rows = (
        await session.execute(
            text(
                """
                SELECT id, t_start,
                       (1.0 - (embedding <=> :vec ::vector)) AS similarity
                FROM events
                WHERE status = 'published'
                  AND embedding IS NOT NULL
                  AND id != :eid
                  AND ABS(t_start - :t_start) <= :window
                ORDER BY embedding <=> :vec ::vector
                LIMIT :k
                """
            ),
            {
                "vec": vec_literal,
                "eid": str(event.id),
                "t_start": event.t_start,
                "window": time_window,
                "k": _TOP_K,
            },
        )
    ).fetchall()

    merged = 0
    for row in rows:
        similarity = float(row.similarity)
        if similarity < threshold:
            break  # ordered by distance; no point checking further
        candidate_id = row.id
        # Merge the newer event into the older one (keep older as canonical).
        newer, older = (
            (event.id, candidate_id)
            if event.t_start >= row.t_start
            else (candidate_id, event.id)
        )
        # Only merge if the newer one is still published (another pass may already merged it).
        affected = (
            await session.execute(
                update(Event)
                .where(Event.id == newer, Event.status == EventStatus.PUBLISHED)
                .values(status=EventStatus.MERGED, merged_into=older)
                .returning(Event.id)
            )
        ).fetchall()
        if affected:
            merged += 1
            log.info(
                "merged event %s → %s (similarity=%.4f)", newer, older, similarity
            )
    return merged


async def run_dedup() -> dict:
    """Embed un-embedded events, then detect and merge near-duplicates."""
    async with session_scope() as session:
        if not await config_service.get(session, "agents.dedup.enabled", True):
            log.info("dedup disabled via config")
            return {"enabled": False}

        batch_size = int(await config_service.get(session, "agents.dedup.batch_size", 50))
        threshold = float(
            await config_service.get(session, "agents.dedup.similarity_threshold", 0.95)
        )
        time_window = float(
            await config_service.get(session, "agents.dedup.time_window_years", 1.0)
        )

        # ── Phase 1: embed ──────────────────────────────────────────────────────
        unembed = (
            await session.execute(
                select(Event)
                .where(
                    Event.status == EventStatus.PUBLISHED,
                    Event.embedding.is_(None),
                )
                .order_by(Event.severity.desc(), Event.created_at.desc())
                .limit(batch_size)
            )
        ).scalars().all()

        totals: dict = {
            "candidates": len(unembed),
            "embedded": 0,
            "pairs_checked": 0,
            "merged": 0,
            "skipped": 0,
        }

        if not unembed:
            log.info("dedup: no un-embedded events")
            return totals

        embedder = await build_embedder(session)
        try:
            totals["embedded"] = await _embed_batch(session, list(unembed), embedder)
        finally:
            await embedder.aclose()

        if totals["embedded"] == 0:
            log.warning("dedup: embed phase produced no vectors; skipping dedup check")
            return totals

        # ── Phase 2: dedup ──────────────────────────────────────────────────────
        for event in unembed:
            if event.embedding is None:
                totals["skipped"] += 1
                continue
            totals["pairs_checked"] += _TOP_K
            totals["merged"] += await _dedup_event(session, event, threshold, time_window)

    log.info("dedup: %s", totals)
    return totals
