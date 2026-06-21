"""Simple Redis-list job queue for admin-portal run-now triggers.

Protocol: LPUSH to ``chronos:run_queue`` (API side); BRPOP to consume (worker side).
Functions accept an injected Redis client so callers control connection lifetime and
tests can substitute a fake.
"""

from __future__ import annotations

import json

QUEUE_KEY = "chronos:run_queue"


def push_job(redis_client, command: str, args: dict | None = None) -> None:
    """Enqueue one agent job (fire-and-forget by the API)."""
    payload = json.dumps({"command": command, "args": args or {}})
    redis_client.lpush(QUEUE_KEY, payload)


def pop_job(redis_client, timeout: float = 0) -> dict | None:
    """Block-pop the next job; returns None on timeout. Suitable for asyncio.to_thread."""
    result = redis_client.brpop(QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _, raw = result
    return json.loads(raw)
