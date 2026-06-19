"""Agent-run recording + queries (the data behind the Admin Portal's "what are they doing /
how healthy are they").

``record_run`` wraps an agent execution: it writes a ``running`` row (committed, so the
portal sees the in-flight run), then finalizes it ``ok``/``error`` with the agent's result
counts. It uses its **own** sessions so it is independent of whatever transactions the agent
runs internally.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import select

from chronos_core.db import session_scope
from chronos_core.models.agent_run import AgentRun


class _Recorder:
    """Handle yielded by record_run; the caller attaches the agent's result stats."""

    def __init__(self, run_id) -> None:
        self.run_id = run_id
        self.stats: dict | None = None

    def set_stats(self, stats) -> None:
        self.stats = stats if isinstance(stats, dict) else None


@asynccontextmanager
async def record_run(component_id: str, command: str):
    """Record one agent execution as an ``agent_runs`` row (running → ok/error)."""
    async with session_scope() as session:
        run = AgentRun(
            component_id=component_id, command=command,
            status="running", started_at=datetime.now(UTC),
        )
        session.add(run)
        await session.flush()
        run_id = run.id

    rec = _Recorder(run_id)
    try:
        yield rec
    except Exception as exc:
        await _finalize(run_id, "error", None, str(exc)[:2000])
        raise
    else:
        await _finalize(run_id, "ok", rec.stats, None)


async def _finalize(run_id, status: str, stats: dict | None, error: str | None) -> None:
    async with session_scope() as session:
        run = await session.get(AgentRun, run_id)
        if run is None:  # pragma: no cover - row should exist
            return
        run.status = status
        run.finished_at = datetime.now(UTC)
        run.stats = stats
        run.error = error


async def recent_runs(session, component_id: str | None = None, *, limit: int = 50):
    """Most-recent runs, optionally for one component."""
    q = select(AgentRun)
    if component_id is not None:
        q = q.where(AgentRun.component_id == component_id)
    q = q.order_by(AgentRun.started_at.desc()).limit(limit)
    return (await session.execute(q)).scalars().all()
