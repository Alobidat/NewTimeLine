"""Source-adapter registry — the growing, first-class source set (event-presentation.md §6).

``all_adapters()`` lists every adapter; ``enabled_adapters(session)`` returns the ones turned
on via ``agents.sources.<id>.enabled`` config (defaults True). Adding a source = adding an
adapter here + its ``agents.sources.<id>.*`` specs — the on-demand collector then queries it
automatically (background and search-driven collection both widen).
"""

from __future__ import annotations

from chronos_core import config_service
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_agents.sources.base import SourceAdapter
from chronos_agents.sources.rss import RssAdapter
from chronos_agents.sources.wikidata import WikidataAdapter
from chronos_agents.sources.wikipedia import WikipediaAdapter


def _enabled_key(adapter_id: str) -> str:
    return f"agents.sources.{adapter_id}.enabled"


async def all_adapters(session: AsyncSession) -> list[SourceAdapter]:
    """Every registered adapter, fully constructed (RSS needs its feed list from config)."""
    feeds = await config_service.get(session, "agents.ingest.rss.feeds", []) or []
    max_clip_width = int(await config_service.get(session, "agents.media.max_clip_width", 720))
    return [
        # media-rich, clip-bearing → collector prefers it first (clips-first, ADR-0023/0024)
        WikipediaAdapter(max_clip_width=max_clip_width),
        WikidataAdapter(),
        RssAdapter(feeds=feeds),
    ]


async def enabled_adapters(session: AsyncSession) -> list[SourceAdapter]:
    """Only adapters whose ``agents.sources.<id>.enabled`` config is truthy (default True)."""
    adapters = await all_adapters(session)
    out: list[SourceAdapter] = []
    for a in adapters:
        if await config_service.get(session, _enabled_key(a.id), True):
            out.append(a)
    return out


async def get_adapter(session: AsyncSession, adapter_id: str) -> SourceAdapter | None:
    """Look up one adapter by id, or None."""
    for a in await all_adapters(session):
        if a.id == adapter_id:
            return a
    return None
