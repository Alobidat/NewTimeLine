"""Token-budget tracking over a rolling time window (ADR-0015).

Only cloud-provider tokens are recorded. When the window's usage reaches the configured
cap, the router switches to the local fallback. Redis is the shared store across workers;
in-memory + null variants exist for tests / unbudgeted setups.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class BudgetTracker(Protocol):
    async def used(self) -> int: ...
    async def add(self, tokens: int) -> None: ...


class NullBudget:
    """No budget tracking (used when no cloud cap is configured)."""

    async def used(self) -> int:
        return 0

    async def add(self, tokens: int) -> None:  # noqa: D102
        return None


class InMemoryBudget:
    """Process-local window tracker — for tests."""

    def __init__(self, window_seconds: int) -> None:
        self.window = window_seconds
        self._buckets: dict[int, int] = {}

    def _key(self) -> int:
        return int(time.time() // self.window)

    async def used(self) -> int:
        return self._buckets.get(self._key(), 0)

    async def add(self, tokens: int) -> None:
        self._buckets[self._key()] = self._buckets.get(self._key(), 0) + tokens


class RedisBudget:
    """Shared window tracker in Redis (key per window, auto-expiring)."""

    def __init__(self, redis, window_seconds: int, prefix: str = "llm:budget") -> None:
        self._redis = redis
        self.window = window_seconds
        self._prefix = prefix

    def _key(self) -> str:
        return f"{self._prefix}:{int(time.time() // self.window)}"

    async def used(self) -> int:
        value = await self._redis.get(self._key())
        return int(value) if value else 0

    async def add(self, tokens: int) -> None:
        key = self._key()
        await self._redis.incrby(key, tokens)
        await self._redis.expire(key, self.window * 2)
