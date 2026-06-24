"""Simple Redis-list job queue for admin-portal run-now triggers.

Protocol: LPUSH to ``chronos:run_queue`` (API side); BRPOP to consume (worker side).
Functions accept an injected Redis client so callers control connection lifetime and
tests can substitute a fake.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("chronos.run_queue")

QUEUE_KEY = "chronos:run_queue"


def push_job(redis_client, command: str, args: dict | None = None) -> None:
    """Enqueue one agent job (fire-and-forget by the API)."""
    payload = json.dumps({"command": command, "args": args or {}})
    redis_client.lpush(QUEUE_KEY, payload)


def enqueue(command: str, args: dict | None = None) -> None:
    """Open a Redis client from settings, push a job, and swallow any failure — for API call
    sites that want true fire-and-forget (never block or fail the request on a queue blip)."""
    try:
        import redis as redislib

        from chronos_core.settings import get_settings

        r = redislib.from_url(get_settings().redis_url)
        try:
            push_job(r, command, args)
        finally:
            r.close()
    except Exception:  # noqa: BLE001 - a down queue must never fail the request
        log.warning("enqueue %s failed", command, exc_info=True)


def pop_job(redis_client, timeout: float = 0) -> dict | None:
    """Block-pop the next job; returns None on timeout. Suitable for asyncio.to_thread."""
    result = redis_client.brpop(QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _, raw = result
    return json.loads(raw)
