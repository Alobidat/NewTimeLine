"""RSS source adapter — full-text-search a feed set for a subject (wraps ingest_rss logic).

RSS feeds have no server-side query, so we poll the configured feeds and keep entries whose
title/summary mention the subject. Reuses ``normalize.normalize_rss`` so the candidates and
their media match every other RSS-sourced event. Not media-rich (some feeds carry images, but
none reliably yield clips), so the collector queries it after the media-rich adapters.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import feedparser

from chronos_agents.normalize import CandidateEvent, normalize_rss
from chronos_agents.sources.base import Capabilities, SourceAdapter, SubjectQuery

log = logging.getLogger("chronos.agents.sources.rss")


def _entry_datetime(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=UTC)


def _matches(entry, needles: list[str]) -> bool:
    """Whether the entry's title/summary contains every search needle (case-insensitive)."""
    hay = f"{entry.get('title') or ''} {entry.get('summary') or ''}".lower()
    return all(n in hay for n in needles)


class RssAdapter(SourceAdapter):
    """Subject search across a configured RSS feed set."""

    id = "rss"
    title = "RSS Feeds"
    capabilities = Capabilities(yields_clips=False, media_rich=False)

    def __init__(self, feeds: list[str]):
        self.feeds = feeds

    async def collect(self, subject: SubjectQuery, *, limit: int) -> list[CandidateEvent]:
        needles = [t for t in subject.text().lower().split() if t]
        out: list[CandidateEvent] = []
        for url in self.feeds:
            if len(out) >= limit:
                break
            try:
                parsed = await asyncio.to_thread(feedparser.parse, url)
            except Exception:
                log.exception("rss adapter: feed failed: %s", url)
                continue
            feed_title = parsed.feed.get("title") if parsed.feed else None
            for entry in parsed.entries:
                if len(out) >= limit:
                    break
                if needles and not _matches(entry, needles):
                    continue
                cand = normalize_rss(
                    {
                        "title": entry.get("title"),
                        "link": entry.get("link"),
                        "summary": entry.get("summary"),
                        "published": _entry_datetime(entry),
                        "media_content": entry.get("media_content"),
                        "media_thumbnail": entry.get("media_thumbnail"),
                        "enclosures": entry.get("enclosures"),
                        "links": entry.get("links"),
                    },
                    feed_publisher=feed_title,
                )
                if cand is not None:
                    out.append(cand)
        return out[:limit]
