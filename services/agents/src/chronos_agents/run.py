"""CLI entrypoint for the Phase-1 agents.

    python -m chronos_agents.run ingest-rss
    python -m chronos_agents.run seed-wikidata --limit 300
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from chronos_core import config_service
from chronos_core.db import session_scope

from chronos_agents.enrich import enrich_pending
from chronos_agents.ingest_rss import ingest_rss
from chronos_agents.seed_wikidata import seed_wikidata


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chronos-agents", description="Chronos Tier-1 agents")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest-rss", help="Poll configured RSS feeds once")
    seed = sub.add_parser("seed-wikidata", help="Seed historical events from Wikidata")
    seed.add_argument("--limit", type=int, default=300)
    sub.add_parser("enrich", help="LLM-enrich a batch of events (Tier-2)")
    return parser


async def _main(args: argparse.Namespace) -> None:
    # Seed Config Service defaults (idempotent) so agents work even if the API hasn't
    # started yet — agents must not depend on the API for their configuration.
    async with session_scope() as session:
        await config_service.ensure_defaults(session)

    if args.command == "ingest-rss":
        print(await ingest_rss())
    elif args.command == "seed-wikidata":
        print(await seed_wikidata(limit=args.limit))
    elif args.command == "enrich":
        print(await enrich_pending())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(_main(_build_parser().parse_args()))


if __name__ == "__main__":
    main()
