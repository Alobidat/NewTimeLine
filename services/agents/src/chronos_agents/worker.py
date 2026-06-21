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

# Default args for queue-triggered runs (no interactive CLI to supply them).
_DEFAULT_ARGS = argparse.Namespace(limit=300)


async def run_worker() -> None:
    """Block-pop jobs from ``chronos:run_queue`` and execute them."""
    # Lazy import to avoid circular deps; run.py imports the agents.
    from chronos_agents.run import _COMMANDS  # noqa: PLC0415

    async with session_scope() as session:
        await config_service.ensure_defaults(session)

    r = redislib.from_url(get_settings().redis_url, decode_responses=True)
    log.info("Agent worker listening on chronos:run_queue …")
    try:
        while True:
            job = await asyncio.to_thread(pop_job, r, 5)
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
                    result = await factory(_DEFAULT_ARGS)
                    rec.set_stats(result)
                log.info("Completed %r → %s", command, result)
            except Exception:
                log.exception("Error running %r", command)
    finally:
        r.close()
