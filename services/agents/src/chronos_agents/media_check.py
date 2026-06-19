"""Media availability + retention checker (Tier-1, no LLM) — the "decide retention later"
half of ADR-0018.

For each due media item it re-checks every host it was seen at, recomputes how confident we
are the media will persist *without* our copy, re-evaluates sensitivity from the (now
possibly enriched) events that cite it, and then:
- **escalates** a link whose hosts have vanished → queue a (best-effort) local capture,
- **upgrades** newly-sensitive media to ``pin`` (and captures it if only linked),
- **releases** a durable, non-sensitive local copy to reclaim storage (keeps the links).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from chronos_core import config_service, objectstore
from chronos_core.db import session_scope
from chronos_core.domain import media_policy
from chronos_core.models.event import Event
from chronos_core.models.media import EventMedia, Media, MediaSource
from sqlalchemy import or_, select

log = logging.getLogger("chronos.agents.media_check")
AGENT = "media:check"


async def _check_url(client: httpx.AsyncClient, url: str) -> str:
    """Probe a URL → ``available`` | ``gone`` | ``unknown`` (conservative: only an explicit
    404/410 counts as gone, so a flaky 403/timeout never makes us discard a copy)."""
    try:
        resp = await client.head(url, follow_redirects=True, timeout=15.0)
        if resp.status_code in (405, 501):  # HEAD unsupported → try a light GET
            resp = await client.get(url, follow_redirects=True, timeout=20.0)
        if resp.status_code < 400:
            return "available"
        if resp.status_code in (404, 410):
            return "gone"
        return "unknown"
    except Exception:
        return "unknown"


async def _reeval_sensitivity(session, media: Media) -> int:
    """Recompute takedown-risk from the events citing this media (they may now be enriched
    with a sharper category/tags). Returns the max; never lowers a manual judgement."""
    rows = (
        await session.execute(
            select(Event.category, Event.tags)
            .join(EventMedia, EventMedia.event_id == Event.id)
            .where(EventMedia.media_id == media.id)
        )
    ).all()
    scores = [
        media_policy.score_sensitivity(r.category, r.tags, source_kind=media.origin_kind)
        for r in rows
    ]
    return max([media.sensitivity, *scores]) if scores else media.sensitivity


async def _check_one(client: httpx.AsyncClient, session, media: Media, threshold: int) -> str:
    """Re-check + apply retention policy to one media item. Returns the action taken."""
    now = datetime.now(UTC)
    sources = (
        await session.execute(select(MediaSource).where(MediaSource.media_id == media.id))
    ).scalars().all()

    any_available = False
    all_gone = bool(sources)
    stable_available = 0
    for src in sources:
        state = await _check_url(client, src.source_url)
        src.avail_state = state
        src.last_checked_at = now
        if state == "available":
            any_available = True
            src.last_available_at = now
            if src.is_stable:
                stable_available += 1
        if state != "gone":
            all_gone = False

    media.last_checked_at = now
    if any_available:
        media.avail_state = "available"
        media.last_available_at = now
    elif all_gone:
        media.avail_state = "gone"

    days = (now - media.created_at).days if media.created_at else 0
    media.persistence_confidence = media_policy.persistence_confidence(stable_available, days)
    media.sensitivity = await _reeval_sensitivity(session, media)

    # Newly-sensitive → pin (and capture if we were only linking).
    if media.sensitivity >= media_policy.PIN_SENSITIVITY and media.disposition != "pin":
        media.disposition = "pin"
        if media.status == "external":
            media.status = "pending"
            return "pinned"

    # A vanished link → try to capture it (may be too late, but attempt).
    if media.status == "external" and media.avail_state == "gone":
        media.disposition = "archive"
        media.status = "pending"
        return "escalated"

    # A durable, non-sensitive local copy → release the binary, keep the links.
    if media.status == "stored" and media_policy.should_release(
        media.disposition, media.sensitivity, media.persistence_confidence,
        pinned=media.pinned, threshold=threshold,
    ):
        if media.storage_key:
            try:
                await objectstore.delete(media.storage_key)
            except Exception:
                log.warning("release: could not delete %s", media.storage_key, exc_info=True)
        media.storage_key = None
        media.status = "released"
        return "released"

    return "checked"


async def check_media() -> dict:
    """Re-check a batch of media due for verification + apply retention. Returns counts."""
    async with session_scope() as session:
        if not await config_service.get(session, "agents.media.check.enabled", True):
            log.info("media check disabled via config")
            return {"enabled": False}
        batch = int(await config_service.get(session, "agents.media.check.batch_size", 50))
        recheck_hours = int(
            await config_service.get(session, "agents.media.check.recheck_hours", 24)
        )
        threshold = int(await config_service.get(session, "agents.media.release_threshold", 70))
        cutoff = datetime.now(UTC) - timedelta(hours=recheck_hours)

        rows = (
            await session.execute(
                select(Media)
                .where(
                    Media.status.in_(["stored", "external"]),
                    or_(Media.last_checked_at.is_(None), Media.last_checked_at < cutoff),
                )
                .order_by(Media.last_checked_at.asc().nullsfirst())
                .limit(batch)
            )
        ).scalars().all()

        totals = {"candidates": len(rows), "released": 0, "escalated": 0, "pinned": 0, "checked": 0}
        async with httpx.AsyncClient(headers={"User-Agent": "ChronosBot/0.1"}) as client:
            for media in rows:
                action = await _check_one(client, session, media, threshold)
                totals[action] = totals.get(action, 0) + 1

    log.info("media check: %s", totals)
    return totals
