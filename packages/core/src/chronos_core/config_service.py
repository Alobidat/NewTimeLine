"""Config Service — DB-backed, versioned, audited runtime settings (ADR-0006).

Agents and APIs read tunables here (budgets, schedules, severity weights, feeds) so they
change without redeploys. Every write appends to ``config_audit`` and bumps ``version``.
See docs/admin-portal.md §2.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.models.config import Config, ConfigAudit

# Phase-1 defaults, seeded once via ensure_defaults(). Scopes group related keys.
DEFAULTS: dict[str, tuple[Any, str]] = {
    # Severity blend weights (see chronos_core.domain.severity).
    "severity.weights": ({"impact": 0.5, "social": 0.2, "corroboration": 0.3}, "severity"),
    # RSS feeds the Phase-1 ingestor polls (no LLM). Add/remove via the admin portal later.
    "agents.ingest.rss.feeds": (
        [
            "http://feeds.bbci.co.uk/news/world/rss.xml",
            "https://www.theguardian.com/world/rss",
            "https://www.aljazeera.com/xml/rss/all.xml",
        ],
        "agent:ingest",
    ),
    "agents.ingest.rss.enabled": (True, "agent:ingest"),
    "agents.ingest.rss.max_items_per_feed": (50, "agent:ingest"),
    # Global daily LLM token budget (enforced from Phase 3; recorded now).
    "budget.llm.daily_tokens": (0, "global"),
}


async def get(session: AsyncSession, key: str, default: Any = None) -> Any:
    """Return a config value, or ``default`` if the key is unset."""
    row = await session.get(Config, key)
    return row.value if row is not None else default


async def get_many(session: AsyncSession, prefix: str) -> dict[str, Any]:
    """Return all config values whose key starts with ``prefix``."""
    result = await session.execute(select(Config).where(Config.key.startswith(prefix)))
    return {row.key: row.value for row in result.scalars()}


async def set_value(
    session: AsyncSession,
    key: str,
    value: Any,
    *,
    scope: str,
    actor: uuid.UUID | None = None,
    note: str | None = None,
) -> None:
    """Upsert a config value, recording the change in ``config_audit`` and bumping version.

    The caller controls the transaction (commit happens in the session scope).
    """
    row = await session.get(Config, key)
    old_value = row.value if row is not None else None
    session.add(
        ConfigAudit(
            key=key, old_value=old_value, new_value=value, changed_by=actor, note=note
        )
    )
    if row is None:
        session.add(Config(key=key, value=value, scope=scope, version=1, updated_by=actor))
    else:
        row.value = value
        row.scope = scope
        row.version += 1
        row.updated_by = actor


async def ensure_defaults(session: AsyncSession) -> int:
    """Seed any missing DEFAULTS. Idempotent. Returns how many keys were created."""
    created = 0
    for key, (value, scope) in DEFAULTS.items():
        if await session.get(Config, key) is None:
            session.add(Config(key=key, value=value, scope=scope, version=1))
            created += 1
    return created
