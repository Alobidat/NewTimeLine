"""Long-running agent worker — consumes jobs from the Redis run queue and executes them.

Start with:
    chronos-agents worker

The Admin Portal's run-now button pushes jobs; the worker pops and dispatches them
sequentially, recording each run in ``agent_runs`` (same as CLI mode).
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import redis as redislib
from chronos_core import config_service
from chronos_core.db import session_scope
from chronos_core.run_queue import pop_job
from chronos_core.runs import record_run
from chronos_core.settings import get_settings

log = logging.getLogger(__name__)

# Baseline args for queue-triggered runs (no interactive CLI). The job's own ``args`` are
# layered on top so subject fields (keyword/location/actor) reach the collect agent.
_BASE_ARGS = {
    "limit": 300, "keyword": None, "location": None, "actor": None,
    # Bot engine jobs: a count (bots to act / personas to make) + an optional explicit bot id.
    "count": 1, "bot_id": None, "posts_per_bot": 2,
}


def _args_from_job(job: dict) -> argparse.Namespace:
    """Build the factory args namespace from baseline + the job's ``args`` payload."""
    return argparse.Namespace(**{**_BASE_ARGS, **(job.get("args") or {})})


async def _bots_ticker() -> None:
    """Periodically run the bot scheduler tick (enqueues post/interact jobs this worker drains).

    Gated by ``bots.enabled`` inside ``bots_tick`` itself; the interval is config-tunable. This is
    the heartbeat that makes the AI-user feed self-sustaining without an external cron.
    """
    from chronos_agents.bots.scheduler import bots_tick  # noqa: PLC0415

    while True:
        try:
            async with session_scope() as session:
                interval = int(
                    await config_service.get(session, "bots.tick_interval_seconds", 600)
                )
            await bots_tick()
        except Exception:
            log.exception("bots ticker error")
            interval = 600
        await asyncio.sleep(max(interval, 30))


async def _maintenance_ticker() -> None:
    """Periodically enqueue the pipeline-maintenance agents so new + backlogged events get
    enriched, placed on the map, embedded/deduped, and graph-linked without manual runs.

    Each agent is batch-bounded and gated by its own ``*.enabled`` config, so this just keeps
    the pipeline draining; the whole ticker is gated by ``agents.maintenance.enabled``. The
    worker drains the resulting jobs from the same queue the admin run-now button uses.
    """
    from chronos_core import run_queue  # noqa: PLC0415

    # Order matters: enrich (summary/entities) → geocode (needs entities) → dedup (embeddings)
    # → relate (shared-entity backbone) → relate-smart (LLM causal chain, needs embeddings).
    # A short stagger avoids hammering the LLM/Nominatim at once.
    pipeline = ("enrich", "geocode", "dedup", "relate", "relate-smart")
    while True:
        try:
            async with session_scope() as session:
                interval = int(
                    await config_service.get(session, "agents.maintenance.interval_seconds", 900)
                )
                enabled = bool(
                    await config_service.get(session, "agents.maintenance.enabled", True)
                )
            if enabled:
                for cmd in pipeline:
                    run_queue.enqueue(cmd, {})
                    await asyncio.sleep(5)
        except Exception:
            log.exception("maintenance ticker error")
            interval = 900
        await asyncio.sleep(max(interval, 60))


async def _monitor_ticker() -> None:
    """Periodically run the health-monitoring collector: probe every component + sample
    container/host resource utilization (CPU/mem/net/disk) into the metric time-series.

    Gated by ``monitoring.enabled``; interval from ``monitoring.collector.interval_seconds``.
    A single Collector instance persists across cycles so it can turn cumulative network/CPU
    counters into per-second rates. Each cycle self-reports as an ``agent:monitor`` run.
    """
    from chronos_core.monitoring import Collector  # noqa: PLC0415

    collector = Collector()
    while True:
        interval = 30
        try:
            async with session_scope() as session:
                interval = int(
                    await config_service.get(session, "monitoring.collector.interval_seconds", 30)
                )
                enabled = bool(await config_service.get(session, "monitoring.enabled", True))
            if enabled:
                async with record_run("agent:monitor", "monitor") as rec:
                    rec.set_stats(await collector.cycle())
        except Exception:
            log.exception("monitor ticker error")
        await asyncio.sleep(max(interval, 5))


async def run_worker() -> None:
    """Block-pop jobs from ``chronos:run_queue`` and execute them.

    Also runs background tickers that periodically schedule AI-user activity (post/interact) and
    pipeline maintenance (enrich/geocode/dedup/relate), so a single long-running worker drains the
    queue, keeps the bot feed alive, and keeps new events enriched + on the map.
    """
    # Lazy import to avoid circular deps; run.py imports the agents.
    from chronos_agents.run import _COMMANDS  # noqa: PLC0415

    async with session_scope() as session:
        await config_service.ensure_defaults(session)

    ticker = asyncio.create_task(_bots_ticker())
    maint = asyncio.create_task(_maintenance_ticker())
    monitor = asyncio.create_task(_monitor_ticker())
    r = redislib.from_url(get_settings().redis_url, decode_responses=True)
    log.info("Agent worker listening on chronos:run_queue …")
    try:
        while True:
            try:
                job = await asyncio.to_thread(pop_job, r, 5)
            except (redislib.exceptions.TimeoutError, redislib.exceptions.ConnectionError):
                # A BRPOP socket-read timeout on an empty queue (or a brief redis blip) just
                # means "no job" — keep polling rather than crash the worker.
                await asyncio.sleep(0.5)
                continue
            if job is None:
                continue
            command = job.get("command", "")
            if command not in _COMMANDS:
                log.warning("Ignoring unknown command %r", command)
                continue
            log.info("Dispatching %r (queue-triggered)", command)
            component_id, factory = _COMMANDS[command]
            try:
                async with record_run(component_id, command) as rec:
                    result = await factory(_args_from_job(job))
                    rec.set_stats(result)
                log.info("Completed %r → %s", command, result)
            except Exception:
                log.exception("Error running %r", command)
    finally:
        ticker.cancel()
        maint.cancel()
        monitor.cancel()
        r.close()
