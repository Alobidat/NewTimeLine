"""Docker Engine API client over the unix socket (no `docker` SDK — just httpx).

Containers *are* the services, so per-component resource metrics come straight from
``GET /containers/{id}/stats``. We map by the ``com.docker.compose.service`` label (which is
project-name independent) rather than container name. Degrades gracefully: if the socket is
not mounted (the worker needs ``/var/run/docker.sock``), every call returns empty and logs
once — probes still run, only container metrics are skipped.
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("chronos.monitoring.docker")

_SOCKET = "/var/run/docker.sock"
_SERVICE_LABEL = "com.docker.compose.service"
_warned = False


def available() -> bool:
    """True when the Docker socket is mounted into this container."""
    return os.path.exists(_SOCKET)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(uds=_SOCKET),
        base_url="http://docker",
        timeout=10.0,
    )


def _cpu_pct(stats: dict) -> float | None:
    """Docker's CPU% formula (cpu delta ÷ system delta × online CPUs)."""
    try:
        cpu = stats["cpu_stats"]
        pre = stats["precpu_stats"]
        cpu_delta = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
        sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
        online = cpu.get("online_cpus") or len(cpu["cpu_usage"].get("percpu_usage") or []) or 1
        if cpu_delta > 0 and sys_delta > 0:
            return (cpu_delta / sys_delta) * online * 100.0
    except (KeyError, TypeError, ZeroDivisionError):
        pass
    return None


def _mem(stats: dict) -> tuple[int | None, int | None]:
    """(rss_bytes, limit_bytes) — usage minus file cache, cgroup v1/v2 tolerant."""
    try:
        ms = stats["memory_stats"]
        usage = ms.get("usage")
        if usage is None:
            return None, None
        detail = ms.get("stats", {})
        cache = detail.get("inactive_file", detail.get("cache", 0))
        return max(int(usage) - int(cache), 0), ms.get("limit")
    except (KeyError, TypeError):
        return None, None


def _net(stats: dict) -> tuple[int, int]:
    """Cumulative (rx_bytes, tx_bytes) summed across the container's interfaces."""
    rx = tx = 0
    for iface in (stats.get("networks") or {}).values():
        rx += int(iface.get("rx_bytes", 0))
        tx += int(iface.get("tx_bytes", 0))
    return rx, tx


async def container_stats() -> dict[str, dict]:
    """Map compose **service name** → one resource snapshot for each running container.

    Snapshot keys: ``cpu_pct`` (%), ``mem_rss_bytes``, ``mem_limit_bytes``,
    ``net_rx_bytes`` / ``net_tx_bytes`` (cumulative counters; the collector turns these into
    per-second rates by diffing successive cycles)."""
    global _warned
    if not available():
        if not _warned:
            log.warning("Docker socket %s not mounted — container metrics disabled", _SOCKET)
            _warned = True
        return {}

    out: dict[str, dict] = {}
    try:
        async with _client() as c:
            containers = (await c.get("/containers/json")).json()
            services = {
                ct["Id"]: (ct.get("Labels") or {}).get(_SERVICE_LABEL)
                for ct in containers
            }
            for cid, service in services.items():
                if not service:
                    continue
                try:
                    stats = (await c.get(f"/containers/{cid}/stats",
                                         params={"stream": "false"})).json()
                except (httpx.HTTPError, ValueError):
                    continue
                rss, limit = _mem(stats)
                rx, tx = _net(stats)
                out[service] = {
                    "cpu_pct": _cpu_pct(stats),
                    "mem_rss_bytes": rss,
                    "mem_limit_bytes": limit,
                    "net_rx_bytes": rx,
                    "net_tx_bytes": tx,
                }
    except (httpx.HTTPError, OSError):
        log.warning("Docker stats query failed", exc_info=True)
    return out


async def container_logs(service: str, tail: int = 200) -> str | None:
    """Return the last ``tail`` stdout/stderr lines for a compose service (on-demand tail).

    Used by the Admin API's log-tail endpoint (Phase B). Returns None if Docker is
    unavailable or the service isn't running."""
    if not available():
        return None
    try:
        async with _client() as c:
            containers = (await c.get("/containers/json")).json()
            cid = next(
                (ct["Id"] for ct in containers
                 if (ct.get("Labels") or {}).get(_SERVICE_LABEL) == service),
                None,
            )
            if cid is None:
                return None
            resp = await c.get(
                f"/containers/{cid}/logs",
                params={"stdout": "true", "stderr": "true", "tail": str(tail),
                        "timestamps": "true"},
            )
            # Multiplexed stream: 8-byte header per frame. Strip non-printable headers crudely.
            return _demux(resp.content)
    except (httpx.HTTPError, OSError):
        log.warning("Docker logs query failed for %s", service, exc_info=True)
        return None


def _demux(raw: bytes) -> str:
    """Decode Docker's multiplexed log stream (8-byte frame headers) to plain text."""
    out, i, n = [], 0, len(raw)
    while i + 8 <= n:
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        i += 8
        out.append(raw[i:i + size].decode("utf-8", "replace"))
        i += size
    text = "".join(out)
    if not text and raw:  # not multiplexed (tty container) — decode directly
        text = raw.decode("utf-8", "replace")
    return text
