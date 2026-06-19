"""Pure health derivation (no I/O): turn an agent's recent runs into a health verdict the
Admin Portal can show. Kept pure so it is trivially unit-testable; the Admin API feeds it
rows from ``agent_runs`` and the current time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DEFAULT_STALE_AFTER_S = 86_400  # a finished agent older than this with no newer run = stale


@dataclass(frozen=True)
class RunInfo:
    """The minimal run facts health depends on."""

    status: str  # running | ok | error
    started_at: datetime
    finished_at: datetime | None = None


@dataclass(frozen=True)
class AgentHealth:
    """Derived health for one component."""

    status: str                    # never | running | ok | stale | error
    last_run_at: datetime | None
    last_status: str | None
    runs: int
    success_rate: float | None     # over finished runs in the window (0..1)


def derive_health(
    runs: list[RunInfo], now: datetime, *, stale_after_s: int = DEFAULT_STALE_AFTER_S
) -> AgentHealth:
    """Compute health from a window of recent runs (any order)."""
    if not runs:
        return AgentHealth("never", None, None, 0, None)

    ordered = sorted(runs, key=lambda r: r.started_at, reverse=True)
    latest = ordered[0]
    finished = [r for r in ordered if r.status in ("ok", "error")]
    success_rate = (
        sum(1 for r in finished if r.status == "ok") / len(finished) if finished else None
    )
    last_at = latest.finished_at or latest.started_at

    if latest.status == "running":
        status = "running"
    elif latest.status == "error":
        status = "error"
    else:
        age = (now - last_at).total_seconds()
        status = "stale" if age > stale_after_s else "ok"

    return AgentHealth(
        status=status,
        last_run_at=last_at,
        last_status=latest.status,
        runs=len(ordered),
        success_rate=success_rate,
    )
