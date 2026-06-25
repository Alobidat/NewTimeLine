"""The monitoring collector — one cycle = probe every component + sample resources + prune.

Run as a worker ticker (chronos_agents.worker) and also on demand via the ``monitor`` agent
command. Holds light in-memory state (previous network counters + CPU jiffies) so it can turn
Docker's cumulative counters into per-second rates across cycles. Everything is best-effort:
a failing probe or an absent Docker socket degrades that slice, never the whole cycle.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sqlalchemy import text

from chronos_core import config_service, registry
from chronos_core.db import session_scope
from chronos_core.models.component_health import ComponentHealth
from chronos_core.models.metric_sample import MetricSample
from chronos_core.monitoring import docker_api, host
from chronos_core.monitoring.probes import HEARTBEAT_KEY, run_probe
from chronos_core.settings import get_settings

log = logging.getLogger("chronos.monitoring.collector")

# Severity ordering for blending probe + threshold verdicts (worst wins).
_LEVEL_RANK = {"ok": 0, "warning": 1, "degraded": 2, "critical": 3}


def _worst(*levels: str) -> str:
    return max(levels, key=lambda lv: _LEVEL_RANK.get(lv, 0), default="ok")


def level_from_metrics(
    component_id: str, metrics: dict, thresholds: dict
) -> tuple[str, str | None]:
    """Worst severity level implied by a component's metrics vs configured thresholds.

    Threshold keys are ``<component_id>.<metric>`` or ``*.<metric>`` → {warning, critical}.
    Returns (level, message) where message names the first breached metric."""
    level, message = "ok", None
    for metric, value in (metrics or {}).items():
        if not isinstance(value, (int, float)):
            continue
        th = thresholds.get(f"{component_id}.{metric}") or thresholds.get(f"*.{metric}")
        if not th:
            continue
        crit, warn = th.get("critical"), th.get("warning")
        hit = None
        if crit is not None and value >= crit:
            hit = "critical"
        elif warn is not None and value >= warn:
            hit = "warning"
        if hit and _LEVEL_RANK[hit] > _LEVEL_RANK[level]:
            level = hit
            message = f"{metric} {value:.0f} ≥ {th.get(hit)}"
    return level, message


class Collector:
    """Stateful resource/health collector. One instance per worker process (rate state)."""

    def __init__(self) -> None:
        self._prev_net: dict[str, tuple[int, int, float]] = {}  # service → (rx, tx, monotonic)
        self._prev_cpu: tuple[int, int] | None = None           # host (total, idle) jiffies

    async def cycle(self) -> dict:
        """Run one full collection cycle. Returns stat counts for the agent-run record."""
        settings = get_settings()
        now = datetime.now(UTC)
        samples: list[MetricSample] = []

        # 0) Refresh the worker heartbeat first so the worker probe reads it fresh.
        self._write_heartbeat(settings)

        # 1) Probe every probe-backed component (verdicts blended with thresholds in step 4).
        probe_results: dict[str, object] = {}
        for m in registry.REGISTRY:
            if m.health_source == "probe" and m.probe:
                probe_results[m.id] = await run_probe(m.probe, settings)

        # 2) Per-container resource samples (Docker stats → rates) + a latest-resource map.
        stats = await docker_api.container_stats()
        svc_to_component = {m.container: m.id for m in registry.REGISTRY if m.container}
        resources: dict[str, dict] = {}
        for service, snap in stats.items():
            component_id = svc_to_component.get(service)
            if component_id is None:
                continue
            samples.extend(self._container_samples(component_id, service, snap, now))
            resources[component_id] = _resource_metrics(snap)

        # 3) Host resource samples.
        samples.extend(self._host_samples(now))

        # 4) Blend probe verdict + threshold verdict per component → upsert health.
        thresholds = await self._load_thresholds()
        async with session_scope() as session:
            for cid, result in probe_results.items():
                merged = {**(result.metrics or {}), **resources.get(cid, {})}
                tlevel, tmsg = level_from_metrics(cid, merged, thresholds)
                level = _worst(result.level, tlevel)
                message = result.message or (tmsg if tlevel != "ok" else None)
                await self._upsert_health(session, cid, result.status, level, message, merged, now)

        # 5) Persist samples + prune retention.
        async with session_scope() as session:
            session.add_all(samples)
        pruned = await self._prune(settings, now)

        log.info("monitor cycle: probed=%d samples=%d", len(probe_results), len(samples))
        return {"probed": len(probe_results), "samples": len(samples), **pruned}

    async def _load_thresholds(self) -> dict:
        try:
            async with session_scope() as session:
                return await config_service.get(session, "monitoring.thresholds", {}) or {}
        except Exception:  # noqa: BLE001
            return {}

    # ── internals ──────────────────────────────────────────────────────────────────────────

    def _write_heartbeat(self, settings) -> None:
        try:
            import redis as redislib  # noqa: PLC0415

            r = redislib.from_url(settings.redis_url)
            try:
                r.set(HEARTBEAT_KEY, str(time.time()))
            finally:
                r.close()
        except Exception:  # noqa: BLE001
            log.warning("heartbeat write failed", exc_info=True)

    async def _upsert_health(self, session, component_id, status, level, message, metrics, now):
        row = await session.get(ComponentHealth, component_id)
        if row is None:
            session.add(ComponentHealth(
                component_id=component_id, status=status, level=level,
                message=message, metrics=metrics or None, checked_at=now,
            ))
        else:
            row.status, row.level, row.message = status, level, message
            row.metrics = metrics or None
            row.checked_at = now

    def _container_samples(self, component_id, service, snap, now) -> list[MetricSample]:
        out: list[MetricSample] = []

        def add(metric, value, unit):
            if value is not None:
                out.append(MetricSample(component_id=component_id, metric=metric,
                                        value=float(value), unit=unit, ts=now))

        add("cpu_pct", snap.get("cpu_pct"), "pct")
        rss, limit = snap.get("mem_rss_bytes"), snap.get("mem_limit_bytes")
        add("mem_rss_bytes", rss, "bytes")
        if rss is not None and limit:
            add("mem_used_pct", rss / limit * 100.0, "pct")

        # Network counters → per-second rates (needs a previous reading).
        rx, tx = snap.get("net_rx_bytes"), snap.get("net_tx_bytes")
        mono = time.monotonic()
        prev = self._prev_net.get(service)
        if prev and rx is not None and tx is not None:
            prx, ptx, pmono = prev
            dt = mono - pmono
            if dt > 0:
                add("net_rx_bytes_per_s", max(rx - prx, 0) / dt, "bytes_per_s")
                add("net_tx_bytes_per_s", max(tx - ptx, 0) / dt, "bytes_per_s")
        if rx is not None and tx is not None:
            self._prev_net[service] = (rx, tx, mono)
        return out

    def _host_samples(self, now) -> list[MetricSample]:
        out: list[MetricSample] = []

        def add(metric, value, unit):
            if value is not None:
                out.append(MetricSample(component_id="host", metric=metric,
                                        value=float(value), unit=unit, ts=now))

        for k, v in host.disk_usage().items():
            add(k, v, "pct" if k.endswith("pct") else "bytes")
        for k, v in host.mem_usage().items():
            add(k, v, "pct" if k.endswith("pct") else "bytes")
        add("load_1m", host.load_avg(), "count")

        cur = host.cpu_times()
        if cur and self._prev_cpu:
            dt_total = cur[0] - self._prev_cpu[0]
            dt_idle = cur[1] - self._prev_cpu[1]
            if dt_total > 0:
                add("cpu_pct", (1 - dt_idle / dt_total) * 100.0, "pct")
        if cur:
            self._prev_cpu = cur
        return out

    async def _prune(self, settings, now) -> dict:
        """Apply retention to metric_sample, log_record, and monitor agent_runs."""
        async with session_scope() as session:
            cfg = config_service
            m_days = int(await cfg.get(session, "monitoring.metric_retention_days", 14))
            l_days = int(await cfg.get(session, "monitoring.log_retention_days", 7))
            max_rows = int(await cfg.get(session, "monitoring.log_buffer_max_rows", 50000))

            pm = await session.execute(text(
                "DELETE FROM metric_sample WHERE ts < now() - make_interval(days => :d)"
            ), {"d": m_days})
            pl = await session.execute(text(
                "DELETE FROM log_record WHERE ts < now() - make_interval(days => :d)"
            ), {"d": l_days})
            # Trim the ring buffer past its row cap (oldest first).
            await session.execute(text(
                "DELETE FROM log_record WHERE id IN ("
                "  SELECT id FROM log_record ORDER BY ts DESC OFFSET :n)"
            ), {"n": max_rows})
            # Keep the monitor's own run history bounded (it records every cycle).
            await session.execute(text(
                "DELETE FROM agent_runs WHERE component_id = 'agent:monitor' "
                "AND started_at < now() - interval '12 hours'"
            ))
        return {"pruned_metrics": pm.rowcount or 0, "pruned_logs": pl.rowcount or 0}


def _resource_metrics(snap: dict) -> dict:
    """The container resource values used for threshold checks (cpu/mem utilization)."""
    out: dict = {}
    cpu = snap.get("cpu_pct")
    if cpu is not None:
        out["cpu_pct"] = cpu
    rss, limit = snap.get("mem_rss_bytes"), snap.get("mem_limit_bytes")
    if rss is not None and limit:
        out["mem_used_pct"] = rss / limit * 100.0
    return out


async def run_monitor() -> dict:
    """One-shot cycle for the ``monitor`` agent command (no cross-cycle rate state)."""
    return await Collector().cycle()
