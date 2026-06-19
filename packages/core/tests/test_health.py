"""Tests for pure agent-health derivation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from chronos_core.domain.health import RunInfo, derive_health

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def test_never_run():
    h = derive_health([], NOW)
    assert h.status == "never" and h.runs == 0 and h.success_rate is None


def test_recent_ok_is_healthy():
    runs = [RunInfo("ok", NOW - timedelta(hours=1), NOW - timedelta(hours=1, minutes=-5))]
    h = derive_health(runs, NOW)
    assert h.status == "ok" and h.success_rate == 1.0


def test_old_success_is_stale():
    runs = [RunInfo("ok", NOW - timedelta(days=3), NOW - timedelta(days=3))]
    assert derive_health(runs, NOW, stale_after_s=86_400).status == "stale"


def test_running_takes_precedence():
    runs = [
        RunInfo("ok", NOW - timedelta(hours=2), NOW - timedelta(hours=2)),
        RunInfo("running", NOW - timedelta(minutes=1)),
    ]
    assert derive_health(runs, NOW).status == "running"


def test_latest_error_surfaces_and_rate_counts_finished():
    runs = [
        RunInfo("ok", NOW - timedelta(hours=3), NOW - timedelta(hours=3)),
        RunInfo("error", NOW - timedelta(minutes=10), NOW - timedelta(minutes=9)),
    ]
    h = derive_health(runs, NOW)
    assert h.status == "error" and h.last_status == "error" and h.success_rate == 0.5
