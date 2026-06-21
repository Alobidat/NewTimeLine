"""CLI entrypoint for the Phase-1/3 agents.

    python -m chronos_agents.run ingest-rss
    python -m chronos_agents.run seed-wikidata --limit 300
    python -m chronos_agents.run enrich
    python -m chronos_agents.run relate
    python -m chronos_agents.run dedup
    python -m chronos_agents.run media-fetch
    python -m chronos_agents.run media-check
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from chronos_core import config_service
from chronos_core.db import session_scope
from chronos_core.runs import record_run

from chronos_agents.dedup import run_dedup
from chronos_agents.geocode import run_geocode
from chronos_agents.enrich import enrich_pending
from chronos_agents.ingest_rss import ingest_rss
from chronos_agents.media_check import check_media
from chronos_agents.media_fetch import fetch_pending
from chronos_agents.relate import link_relations
from chronos_agents.seed_iran_us import seed_iran_us
from chronos_agents.seed_wikidata import seed_wikidata

# command → (component id, coroutine factory). One place to map CLI ↔ registry component.
_COMMANDS = {
    "ingest-rss": ("agent:ingest.rss", lambda a: ingest_rss()),
    "seed-wikidata": ("agent:seed.wikidata", lambda a: seed_wikidata(limit=a.limit)),
    "enrich": ("agent:enrich", lambda a: enrich_pending()),
    "relate": ("agent:relate", lambda a: link_relations()),
    "dedup": ("agent:dedup", lambda a: run_dedup()),
    "geocode": ("agent:geocode", lambda a: run_geocode()),
    "media-fetch": ("agent:media.fetch", lambda a: fetch_pending()),
    "media-check": ("agent:media.check", lambda a: check_media()),
    "seed-iran-us": ("agent:seed.iran-us", lambda a: seed_iran_us()),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chronos-agents", description="Chronos Tier-1 agents")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest-rss", help="Poll configured RSS feeds once")
    seed = sub.add_parser("seed-wikidata", help="Seed historical events from Wikidata")
    seed.add_argument("--limit", type=int, default=300)
    sub.add_parser("enrich", help="LLM-enrich a batch of events (Tier-2)")
    sub.add_parser("relate", help="Link events into the history graph from shared entities")
    sub.add_parser("dedup", help="Embed events + merge near-duplicates via pgvector")
    sub.add_parser("media-fetch", help="Download media flagged for local capture (ADR-0018)")
    sub.add_parser("media-check", help="Re-check media availability + apply retention policy")
    sub.add_parser("seed-iran-us", help="Seed the curated US–Iran PoC history web")
    sub.add_parser("geocode", help="Geocode events + place entities via Nominatim (OSM)")
    return parser


async def _main(args: argparse.Namespace) -> None:
    # Seed Config Service defaults (idempotent) so agents work even if the API hasn't
    # started yet — agents must not depend on the API for their configuration.
    async with session_scope() as session:
        await config_service.ensure_defaults(session)

    component_id, factory = _COMMANDS[args.command]
    # Record the execution (running → ok/error) so the Admin Portal sees health + history.
    async with record_run(component_id, args.command) as rec:
        result = await factory(args)
        rec.set_stats(result)
    print(result)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(_main(_build_parser().parse_args()))


if __name__ == "__main__":
    main()
