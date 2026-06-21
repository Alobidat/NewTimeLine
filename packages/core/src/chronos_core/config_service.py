"""Config Service — DB-backed, versioned, audited runtime settings (ADR-0006).

Agents and APIs read tunables here (budgets, schedules, severity weights, feeds) so they
change without redeploys. Every write appends to ``config_audit`` and bumps ``version``.
See docs/admin-portal.md §2.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from chronos_core.config_spec import SPECS
from chronos_core.models.config import Config, ConfigAudit

# Seed defaults are derived from the config specs (single source of truth — ADR-0019).
# Each value is (default, scope); ensure_defaults() seeds any missing keys.
DEFAULTS: dict[str, tuple[Any, str]] = {s.key: (s.default, s.scope) for s in SPECS}


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

    Defensive against in-place JSON mutation: callers commonly read a value via :func:`get`,
    mutate it, and pass it back. The stored value is then the *same object* SQLAlchemy already
    holds, so a plain ``row.value = value`` assignment isn't seen as a change and the JSON
    column never flushes. We snapshot ``old_value`` and ``flag_modified`` the column so the new
    value always persists and the audit captures the genuine before-state.
    """
    row = await session.get(Config, key)
    # Deep-copy the prior value: if the caller mutated the stored object in place, a shallow
    # reference would make the audit's old_value identical to the new value.
    old_value = copy.deepcopy(row.value) if row is not None else None
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
        # Force a dirty flag even when `value is row.value` (in-place mutation) so JSON flushes.
        flag_modified(row, "value")


async def ensure_defaults(session: AsyncSession) -> int:
    """Seed any missing DEFAULTS. Idempotent. Returns how many keys were created."""
    created = 0
    for key, (value, scope) in DEFAULTS.items():
        if await session.get(Config, key) is None:
            session.add(Config(key=key, value=value, scope=scope, version=1))
            created += 1
    return created
