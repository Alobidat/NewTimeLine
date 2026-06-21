"""Media-fetcher (Tier-1, no LLM): download media flagged for local capture into the
object store — the "capture first" half of ADR-0018.

Processes ``media`` rows with ``status='pending'`` and a store disposition (``pin`` /
``archive``), most-sensitive first (those vanish soonest). Dedups identical binaries by
content hash so two events citing the same image share one stored object. Over-large
binaries (e.g. full videos) are left as external links rather than stored.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime

import httpx
from chronos_core import config_service, objectstore
from chronos_core.db import session_scope
from chronos_core.domain.thumbnails import is_image_mime, make_thumbnail
from chronos_core.models.media import Media
from sqlalchemy import select

log = logging.getLogger("chronos.agents.media_fetch")
AGENT = "media:fetch"


async def _store_one(client: httpx.AsyncClient, session, media: Media, max_bytes: int) -> str:
    """Download + store one media binary. Returns the resulting status."""
    if media.kind == "embed" or not media.source_url:
        return "external"  # external player — nothing to download
    resp = await client.get(media.source_url, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    data = resp.content
    now = datetime.now(UTC)
    media.last_checked_at = now
    if len(data) > max_bytes:
        # Too big to archive cheaply (likely full video): keep linking to the origin.
        media.embed_url = media.source_url
        return "external"

    digest = hashlib.sha256(data).hexdigest()[:64]
    content_type = media.mime or resp.headers.get("content-type")

    # Dedup: if an identical binary is already stored, point at the same object.
    twin = await session.scalar(
        select(Media).where(Media.content_hash == digest, Media.id != media.id)
    )
    if twin is not None and twin.storage_key:
        media.storage_key = twin.storage_key
    else:
        key = f"media/{media.id}"
        await asyncio.to_thread(
            objectstore.put_bytes, key, data, content_type=content_type
        )
        media.storage_key = key
        media.content_hash = digest

    media.bytes = len(data)
    media.mime = content_type
    media.avail_state = "available"
    media.last_available_at = now

    # Generate a thumbnail for stored images so the UI can show previews cheaply.
    if media.kind == "image" and is_image_mime(content_type) and not media.thumbnail_key:
        try:
            thumb_bytes, _ = make_thumbnail(data)
            thumb_key = f"media/{media.id}_thumb.jpg"
            await asyncio.to_thread(
                objectstore.put_bytes, thumb_key, thumb_bytes, content_type="image/jpeg"
            )
            media.thumbnail_key = thumb_key
        except Exception:
            log.warning("thumbnail generation failed for %s", media.id, exc_info=True)

    return "stored"


async def fetch_pending() -> dict:
    """Capture a batch of pending store-disposition media. Returns counts."""
    async with session_scope() as session:
        if not await config_service.get(session, "agents.media.fetch.enabled", True):
            log.info("media fetch disabled via config")
            return {"enabled": False}
        batch = int(await config_service.get(session, "agents.media.fetch.batch_size", 20))
        max_bytes = int(
            await config_service.get(session, "agents.media.fetch.max_bytes", 26_214_400)
        )

        rows = (
            await session.execute(
                select(Media)
                .where(Media.status == "pending", Media.disposition.in_(["pin", "archive"]))
                .order_by(Media.sensitivity.desc(), Media.created_at)
                .limit(batch)
            )
        ).scalars().all()

        totals = {"candidates": len(rows), "stored": 0, "external": 0, "failed": 0}
        # Descriptive UA — Wikimedia and others 403 generic/empty agents.
        ua = "ChronosBot/0.1 (+https://github.com/Alobidat/NewTimeLine) media-fetch"
        async with httpx.AsyncClient(headers={"User-Agent": ua}) as client:
            for media in rows:
                try:
                    media.status = await _store_one(client, session, media, max_bytes)
                    totals["stored" if media.status == "stored" else "external"] += 1
                except Exception:
                    log.warning("media fetch failed: %s", media.source_url, exc_info=True)
                    media.status = "failed"
                    media.last_checked_at = datetime.now(UTC)
                    totals["failed"] += 1
                await session.flush()

    log.info("media fetch: %s", totals)
    return totals
