"""CLI entrypoint for the Phase-1 agents.

    python -m chronos_agents.run ingest-rss
    python -m chronos_agents.run seed-wikidata --limit 300
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from chronos_agents.ingest_rss import ingest_rss
from chronos_agents.seed_wikidata import seed_wikidata


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chronos-agents", description="Chronos Tier-1 agents")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest-rss", help="Poll configured RSS feeds once")
    seed = sub.add_parser("seed-wikidata", help="Seed historical events from Wikidata")
    seed.add_argument("--limit", type=int, default=300)
    return parser


async def _main(args: argparse.Namespace) -> None:
    if args.command == "ingest-rss":
        print(await ingest_rss())
    elif args.command == "seed-wikidata":
        print(await seed_wikidata(limit=args.limit))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(_main(_build_parser().parse_args()))


if __name__ == "__main__":
    main()
