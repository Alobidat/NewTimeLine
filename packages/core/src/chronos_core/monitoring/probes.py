"""Live health probes for infra + runtime services.

Each probe returns a ``ProbeResult`` (status + severity level + message + metrics dict). The
collector runs the probe declared by a manifest's ``probe`` descriptor and upserts the result
into ``component_health``. Probes use only deps already in chronos-core (httpx / redis /
boto3) and never raise — a failure becomes a ``down``/``critical`` verdict, not a crash.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from sqlalchemy import text

from chronos_core.db import session_scope
from chronos_core.settings import Settings

log = logging.getLogger("chronos.monitoring.probes")

# Heartbeat key the collector refreshes each cycle (read by the worker probe).
HEARTBEAT_KEY = "chronos:monitor:heartbeat"


@dataclass
class ProbeResult:
    status: str                       # ok | down | degraded | unknown
    level: str = "ok"                 # ok | warning | degraded | critical
    message: str | None = None
    metrics: dict = field(default_factory=dict)


_DOWN = lambda msg: ProbeResult("down", "critical", msg)  # noqa: E731


async def probe_postgres(_: dict, settings: Settings) -> ProbeResult:
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
            size = await session.scalar(text("SELECT pg_database_size(current_database())"))
            conns = await session.scalar(text("SELECT count(*) FROM pg_stat_activity"))
        return ProbeResult("ok", "ok", None,
                           {"db_size_bytes": int(size or 0), "connections": int(conns or 0)})
    except Exception as exc:  # noqa: BLE001
        return _DOWN(str(exc)[:200])


async def probe_redis(_: dict, settings: Settings) -> ProbeResult:
    import redis as redislib  # noqa: PLC0415

    def _check() -> dict:
        r = redislib.from_url(settings.redis_url)
        try:
            r.ping()
            mem = r.info("memory")
            clients = r.info("clients")
            return {
                "used_memory_bytes": int(mem.get("used_memory", 0)),
                "connected_clients": int(clients.get("connected_clients", 0)),
            }
        finally:
            r.close()

    try:
        return ProbeResult("ok", "ok", None, await asyncio.to_thread(_check))
    except Exception as exc:  # noqa: BLE001
        return _DOWN(str(exc)[:200])


async def probe_rabbitmq(_: dict, settings: Settings) -> ProbeResult:
    # Reach the management API on :15672 using the AMQP credentials/host.
    u = urlparse(settings.amqp_url)
    host = u.hostname or "rabbitmq"
    auth = (u.username or "guest", u.password or "guest")
    base = f"http://{host}:15672/api"
    try:
        async with httpx.AsyncClient(timeout=8.0, auth=auth) as c:
            node = await c.get(f"{base}/healthchecks/node")
            ok = node.status_code == 200 and node.json().get("status") == "ok"
            metrics: dict = {}
            try:
                ov = (await c.get(f"{base}/overview")).json()
                qt = ov.get("queue_totals", {})
                metrics = {
                    "messages": int(qt.get("messages", 0)),
                    "messages_ready": int(qt.get("messages_ready", 0)),
                    "connections": int(ov.get("object_totals", {}).get("connections", 0)),
                }
            except (httpx.HTTPError, ValueError, KeyError):
                pass
        if ok:
            return ProbeResult("ok", "ok", None, metrics)
        return ProbeResult("degraded", "degraded", "node healthcheck not ok", metrics)
    except Exception as exc:  # noqa: BLE001
        return _DOWN(str(exc)[:200])


async def probe_object(_: dict, settings: Settings) -> ProbeResult:
    import boto3  # noqa: PLC0415
    from botocore.config import Config as BotoConfig  # noqa: PLC0415

    def _check() -> None:
        s3 = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=BotoConfig(connect_timeout=5, read_timeout=5, retries={"max_attempts": 1}),
        )
        s3.head_bucket(Bucket=settings.s3_bucket)

    try:
        await asyncio.to_thread(_check)
        return ProbeResult("ok", "ok", None, {})
    except Exception as exc:  # noqa: BLE001
        return _DOWN(str(exc)[:200])


async def probe_http(probe: dict, settings: Settings) -> ProbeResult:
    live = probe.get("live")
    ready = probe.get("ready")
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            t0 = time.monotonic()
            resp = await c.get(live)
            latency_ms = (time.monotonic() - t0) * 1000.0
            metrics = {"latency_ms": round(latency_ms, 1), "http_status": resp.status_code}
            if resp.status_code >= 500:
                return ProbeResult("down", "critical", f"HTTP {resp.status_code}", metrics)
            if ready:
                rr = await c.get(ready)
                metrics["ready_status"] = rr.status_code
                if rr.status_code >= 500:
                    return ProbeResult("degraded", "degraded", "not ready", metrics)
            return ProbeResult("ok", "ok", None, metrics)
    except Exception as exc:  # noqa: BLE001
        return _DOWN(str(exc)[:200])


async def probe_heartbeat(probe: dict, settings: Settings) -> ProbeResult:
    import redis as redislib  # noqa: PLC0415

    key = probe.get("key", HEARTBEAT_KEY)
    stale_after = float(probe.get("stale_after_s", 120))

    def _read() -> float | None:
        r = redislib.from_url(settings.redis_url)
        try:
            v = r.get(key)
            return float(v) if v is not None else None
        finally:
            r.close()

    try:
        ts = await asyncio.to_thread(_read)
        if ts is None:
            return ProbeResult("unknown", "warning", "no heartbeat yet")
        age = max(time.time() - ts, 0.0)
        metrics = {"heartbeat_age_s": round(age, 1)}
        if age > stale_after:
            return ProbeResult("down", "critical", f"heartbeat stale ({age:.0f}s)", metrics)
        return ProbeResult("ok", "ok", None, metrics)
    except Exception as exc:  # noqa: BLE001
        return _DOWN(str(exc)[:200])


PROBES = {
    "postgres": probe_postgres,
    "redis": probe_redis,
    "rabbitmq": probe_rabbitmq,
    "object": probe_object,
    "http": probe_http,
    "heartbeat": probe_heartbeat,
}


async def run_probe(probe: dict, settings: Settings) -> ProbeResult:
    """Dispatch a probe descriptor to its implementation (unknown type → ``unknown``)."""
    fn = PROBES.get(probe.get("type"))
    if fn is None:
        return ProbeResult("unknown", "warning", f"no probe for {probe.get('type')!r}")
    return await fn(probe, settings)
