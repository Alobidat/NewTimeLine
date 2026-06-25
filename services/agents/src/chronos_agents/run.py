"""CLI entrypoint for the Phase-1/3 agents.

    python -m chronos_agents.run ingest-rss
    python -m chronos_agents.run seed-wikidata --limit 300
    python -m chronos_agents.run enrich
    python -m chronos_agents.run relate
    python -m chronos_agents.run dedup
    python -m chronos_agents.run media-fetch
    python -m chronos_agents.run media-check
    python -m chronos_agents.run media-gap
    python -m chronos_agents.run collect --keyword "..." --location "..." --actor "..."
    python -m chronos_agents.run worker   # long-running queue consumer
"""

from __future__ import annotations

import argparse
import asyncio

from chronos_core import config_service
from chronos_core.db import session_scope
from chronos_core.logging_setup import init_logging
from chronos_core.monitoring import run_monitor
from chronos_core.runs import record_run

from chronos_agents.bots.bootstrap import bootstrap as bots_bootstrap
from chronos_agents.bots.interact import persona_interact
from chronos_agents.bots.post import persona_post
from chronos_agents.bots.scheduler import bots_tick
from chronos_agents.dedup import run_dedup
from chronos_agents.enrich import enrich_pending
from chronos_agents.geocode import run_geocode
from chronos_agents.ingest_rss import ingest_rss
from chronos_agents.media_check import check_media
from chronos_agents.media_fetch import fetch_pending
from chronos_agents.media_gap import flag_media_gaps
from chronos_agents.media_quality import improve_media
from chronos_agents.moderation import moderate_comment, moderate_event, moderate_pending
from chronos_agents.persona_gen import generate_personas
from chronos_agents.relate import link_relations
from chronos_agents.relate_smart import run_smart_relate
from chronos_agents.seed_iran_us import seed_iran_us
from chronos_agents.seed_video import seed_video
from chronos_agents.seed_wikidata import seed_wikidata
from chronos_agents.sources.base import SubjectQuery
from chronos_agents.sources.collect import run_collect


def _subject_from_args(a) -> SubjectQuery:
    """Build a SubjectQuery from CLI args OR queue-job args (both expose the same names)."""
    return SubjectQuery(
        keyword=getattr(a, "keyword", None),
        location=getattr(a, "location", None),
        actor=getattr(a, "actor", None),
    )


# command → (component id, coroutine factory). One place to map CLI ↔ registry component.
# Factories take the parsed args namespace, so queue jobs can pass their args through too.
_COMMANDS = {
    "ingest-rss": ("agent:ingest.rss", lambda a: ingest_rss()),
    "seed-wikidata": ("agent:seed.wikidata", lambda a: seed_wikidata(limit=a.limit)),
    "enrich": ("agent:enrich", lambda a: enrich_pending()),
    "relate": ("agent:relate", lambda a: link_relations()),
    "relate-smart": ("agent:relate.smart", lambda a: run_smart_relate()),
    "dedup": ("agent:dedup", lambda a: run_dedup()),
    "geocode": ("agent:geocode", lambda a: run_geocode()),
    "media-fetch": ("agent:media.fetch", lambda a: fetch_pending()),
    "media-check": ("agent:media.check", lambda a: check_media()),
    "media-gap": ("agent:media.gap", lambda a: flag_media_gaps()),
    "media-quality": (
        "agent:media.quality", lambda a: improve_media(full=getattr(a, "full", False)),
    ),
    "collect": ("agent:collect", lambda a: run_collect(_subject_from_args(a))),
    "seed-iran-us": ("agent:seed.iran-us", lambda a: seed_iran_us()),
    "seed-video": (
        "agent:seed.video",
        lambda a: seed_video(per_topic=a.per_topic, max_total=a.max_total),
    ),
    "persona-gen": ("agent:persona.gen", lambda a: generate_personas(count=a.count)),
    "persona-post": (
        "agent:bots.post",
        lambda a: persona_post(bot_id=getattr(a, "bot_id", None), count=a.count),
    ),
    "persona-interact": (
        "agent:bots.interact",
        lambda a: persona_interact(bot_id=getattr(a, "bot_id", None), count=a.count),
    ),
    "moderate-event": (
        "agent:moderation",
        lambda a: moderate_event(getattr(a, "event_id", None)),
    ),
    "moderate-comment": (
        "agent:moderation",
        lambda a: moderate_comment(getattr(a, "comment_id", None)),
    ),
    "moderate-pending": ("agent:moderation", lambda a: moderate_pending()),
    "monitor": ("agent:monitor", lambda a: run_monitor()),
    "bots-tick": ("agent:bots.scheduler", lambda a: bots_tick()),
    "bots-bootstrap": (
        "agent:bots.scheduler",
        lambda a: bots_bootstrap(count=a.count, posts_per_bot=getattr(a, "posts_per_bot", 2)),
    ),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chronos-agents", description="Chronos Tier-1 agents")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest-rss", help="Poll configured RSS feeds once")
    seed = sub.add_parser("seed-wikidata", help="Seed historical events from Wikidata")
    seed.add_argument("--limit", type=int, default=300)
    sub.add_parser("enrich", help="LLM-enrich a batch of events (Tier-2)")
    sub.add_parser("relate", help="Link events into the history graph from shared entities")
    sub.add_parser("relate-smart", help="LLM-build the causal history chain")
    sub.add_parser("dedup", help="Embed events + merge near-duplicates via pgvector")
    sub.add_parser("media-fetch", help="Download media flagged for local capture (ADR-0018)")
    sub.add_parser("media-check", help="Re-check media availability + apply retention policy")
    mq = sub.add_parser("media-quality",
                        help="Quality guard: measure widths, upgrade/hold low-quality heroes")
    mq.add_argument("--all", action="store_true", dest="full",
                    help="Sweep the whole published corpus (one-time backlog clean-up)")
    sub.add_parser("seed-iran-us", help="Seed the curated US–Iran PoC history web")
    sv = sub.add_parser("seed-video", help="Seed video-hero events from Wikimedia Commons")
    sv.add_argument("--per-topic", type=int, default=6, help="Clips to pull per topic")
    sv.add_argument("--max-total", type=int, default=100, help="Max events to seed")
    sub.add_parser("geocode", help="Geocode events + place entities via Nominatim (OSM)")
    sub.add_parser("media-gap", help="Re-collect media for text-only events (clips-first)")
    pg = sub.add_parser("persona-gen", help="Generate AI-user personas + avatars")
    pg.add_argument("--count", type=int, default=20, help="How many personas to create")
    pp = sub.add_parser("persona-post", help="Have AI users discover + post free clips")
    pp.add_argument("--bot-id", default=None, help="A specific bot user id (else: overdue bots)")
    pp.add_argument("--count", type=int, default=1, help="Bots to act when no --bot-id")
    pi = sub.add_parser("persona-interact", help="Have AI users react/comment/follow")
    pi.add_argument("--bot-id", default=None, help="A specific bot user id (else: overdue bots)")
    pi.add_argument("--count", type=int, default=1, help="Bots to act when no --bot-id")
    sub.add_parser("bots-tick", help="Scheduler tick: enqueue jobs for overdue bots")
    bb = sub.add_parser("bots-bootstrap", help="Bulk-create AI users + seed their first posts")
    bb.add_argument("--count", type=int, default=50, help="How many personas to create")
    bb.add_argument("--posts-per-bot", type=int, default=2, help="Initial posts per bot")
    collect = sub.add_parser(
        "collect", help="On-demand collect events for a subject from all enabled adapters"
    )
    collect.add_argument("--keyword", default=None, help="Event keyword to search")
    collect.add_argument("--location", default=None, help="Location (country/city/area)")
    collect.add_argument("--actor", default=None, help="Actor name(s)")
    me = sub.add_parser("moderate-event", help="LLM-moderate one event (by --event-id)")
    me.add_argument("--event-id", default=None, dest="event_id")
    mc = sub.add_parser("moderate-comment", help="LLM-moderate one comment (by --comment-id)")
    mc.add_argument("--comment-id", default=None, dest="comment_id")
    sub.add_parser("moderate-pending", help="Batch-moderate recent user events (backstop)")
    sub.add_parser("monitor", help="Run one health-monitor cycle (probe + sample resources)")
    sub.add_parser("worker", help="Long-running queue worker (consumes admin run-now jobs)")
    return parser


async def _main(args: argparse.Namespace) -> None:
    if args.command == "worker":
        from chronos_agents.worker import run_worker  # noqa: PLC0415
        await run_worker()
        return

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
    init_logging("service:worker")
    asyncio.run(_main(_build_parser().parse_args()))


if __name__ == "__main__":
    main()
