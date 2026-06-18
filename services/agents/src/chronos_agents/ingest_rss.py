"""Tier-1 RSS ingestor: fetch feeds → store raw items → normalize → publish (no LLM).

Feeds + limits are read from the Config Service so operators tune them without redeploys
(docs/admin-portal.md). Raw items are kept in ingest_items for audit/replay.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import feedparser
from chronos_core import config_service
from chronos_core.db import session_scope
from chronos_core.models.enums import IngestState
from chronos_core.models.ingest import IngestItem
from sqlalchemy import select

from chronos_agents.normalize import normalize_rss
from chronos_agents.publish import load_weights, publish_candidate

log = logging.getLogger("chronos.agents.ingest_rss")
AGENT = "ingest:rss"


def _entry_datetime(entry) -> datetime | None:
    """Best-effort publication datetime from a feedparser entry (UTC)."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=UTC)


async def _ingest_feed(url: str, max_items: int, weights) -> tuple[int, int]:
    """Process one feed in its own transaction. Returns (published, skipped)."""
    parsed = await asyncio.to_thread(feedparser.parse, url)
    feed_title = parsed.feed.get("title") if parsed.feed else None
    published = skipped = 0

    async with session_scope() as session:
        for entry in parsed.entries[:max_items]:
            external_id = entry.get("id") or entry.get("link")
            if not external_id:
                continue
            seen = await session.scalar(
                select(IngestItem.id).where(
                    IngestItem.feed == url, IngestItem.external_id == external_id
                )
            )
            if seen is not None:
                skipped += 1
                continue

            when = _entry_datetime(entry)
            item = IngestItem(
                feed=url,
                external_id=external_id,
                raw={
                    "title": entry.get("title"),
                    "link": entry.get("link"),
                    "summary": entry.get("summary"),
                    "published": when.isoformat() if when else None,
                },
            )
            session.add(item)

            cand = normalize_rss(
                {
                    "title": entry.get("title"),
                    "link": entry.get("link"),
                    "summary": entry.get("summary"),
                    "published": when,
                },
                feed_publisher=feed_title,
            )
            event = (
                await publish_candidate(session, cand, agent_name=AGENT, weights=weights)
                if cand
                else None
            )
            if event is not None:
                item.state = IngestState.PUBLISHED
                published += 1
            else:
                item.state = IngestState.DISCARDED
                skipped += 1
    return published, skipped


async def ingest_rss() -> dict:
    """Poll all configured RSS feeds once. Returns a summary of counts."""
    async with session_scope() as session:
        if not await config_service.get(session, "agents.ingest.rss.enabled", True):
            log.info("rss ingest disabled via config")
            return {"enabled": False}
        feeds = await config_service.get(session, "agents.ingest.rss.feeds", []) or []
        max_items = int(
            await config_service.get(session, "agents.ingest.rss.max_items_per_feed", 50)
        )
        weights = await load_weights(session)

    totals = {"feeds": len(feeds), "published": 0, "skipped": 0}
    for url in feeds:
        try:
            pub, skip = await _ingest_feed(url, max_items, weights)
            totals["published"] += pub
            totals["skipped"] += skip
            log.info("feed %s: +%d published, %d skipped", url, pub, skip)
        except Exception:  # one bad feed must not stop the rest
            log.exception("feed failed: %s", url)
    return totals
