"""Admin API — the control plane the Admin Portal renders from (ADR-0019).

Generic, manifest/spec-driven endpoints (every call gated by ``require_admin`` and config
writes audited via the Config Service): system overview, component health + control,
schema-driven config read/write, run history, storage, and system status. New backend
components appear here automatically by registering a manifest + config specs — no new
routes needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import redis as redislib
from chronos_core import config_service, registry
from chronos_core.config_spec import SPEC_BY_KEY, validate_value
from chronos_core.db import session_scope
from chronos_core.monitoring import docker_api
from chronos_core.run_queue import QUEUE_KEY, push_job
from chronos_core.runs import recent_runs
from chronos_core.schemas.admin import (
    ComponentDetail,
    ComponentView,
    ConfigEntry,
    ConfigUpdate,
    HealthTreeView,
    HostMetricsView,
    LogLevelUpdate,
    LogLevelView,
    LogRecordView,
    MetricSeries,
    OverviewView,
    RunView,
    StorageView,
    SystemView,
)
from chronos_core.settings import get_settings
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api import admin_queries as aq
from chronos_api.deps import get_session, require_admin

log = logging.getLogger("chronos.api.admin")

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/overview", response_model=OverviewView)
async def overview(session: AsyncSession = Depends(get_session)) -> OverviewView:
    """Landing summary: component health, headline counts, recent activity."""
    now = datetime.now(UTC)
    values = await aq.all_config_values(session)
    components = [await aq.component_view(session, m, now, values) for m in registry.REGISTRY]
    runs = [aq._run_view(r) for r in await recent_runs(session, limit=15)]
    return OverviewView(components=components, counts=await aq.counts(session), recent_runs=runs)


@router.get("/components", response_model=list[ComponentView])
async def list_components(
    kind: str | None = Query(default=None, description="agent | service | store"),
    session: AsyncSession = Depends(get_session),
) -> list[ComponentView]:
    """All managed components (manifest + enabled state + health)."""
    now = datetime.now(UTC)
    values = await aq.all_config_values(session)
    return [await aq.component_view(session, m, now, values) for m in registry.components(kind)]


@router.get("/components/{component_id}", response_model=ComponentDetail)
async def component_detail(
    component_id: str, session: AsyncSession = Depends(get_session)
) -> ComponentDetail:
    """One component: manifest + enabled state + health + its config + recent runs."""
    m = registry.get(component_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown component")
    now = datetime.now(UTC)
    values = await aq.all_config_values(session)
    base = await aq.component_view(session, m, now, values)
    runs = [aq._run_view(r) for r in await recent_runs(session, component_id, limit=25)]
    return ComponentDetail(
        **base.model_dump(),
        config=aq.config_entries(values, component_id=component_id),
        recent_runs=runs,
    )


@router.post("/components/{component_id}/actions/{action}")
async def component_action(
    component_id: str,
    action: str,
    actor: str = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run a declared action. enable/disable/pause toggle the component's config flag;
    run-now pushes a job to the Redis queue consumed by the agent worker."""
    m = registry.get(component_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown component")
    if action not in m.actions:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported action: {action}")

    if action in ("enable", "disable", "pause"):
        if not m.enabled_key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "component has no enabled flag")
        new_value = action == "enable"
        spec = SPEC_BY_KEY.get(m.enabled_key)
        await config_service.set_value(
            session, m.enabled_key, new_value,
            scope=spec.scope if spec else "global", note=f"{actor}:{action}",
        )
        return {"component": component_id, "action": action, "enabled": new_value}

    if action == "run-now":
        if not m.command:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "component has no runnable command")
        r = redislib.from_url(get_settings().redis_url)
        try:
            await asyncio.to_thread(push_job, r, m.command)
        finally:
            await asyncio.to_thread(r.close)
        return {"component": component_id, "action": "run-now", "queued": True, "command": m.command}

    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported action: {action}")


@router.get("/config", response_model=list[ConfigEntry])
async def get_config(
    scope: str | None = None,
    component: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ConfigEntry]:
    """All config entries (spec + current value), optionally filtered by scope/component."""
    values = await aq.all_config_values(session)
    return aq.config_entries(values, component_id=component, scope=scope)


@router.put("/config/{key}", response_model=ConfigEntry)
async def put_config(
    key: str,
    body: ConfigUpdate,
    actor: str = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ConfigEntry:
    """Validate a config value against its spec and persist it (audited + version-bumped)."""
    spec = SPEC_BY_KEY.get(key)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown config key")
    ok, err = validate_value(key, body.value)
    if not ok:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, err or "invalid value")
    await config_service.set_value(
        session, key, body.value, scope=spec.scope, note=f"{actor}:config"
    )
    values = await aq.all_config_values(session)
    return next(e for e in aq.config_entries(values) if e.key == key)


@router.get("/runs", response_model=list[RunView])
async def list_runs(
    component: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[RunView]:
    """Recent agent runs (optionally for one component)."""
    return [aq._run_view(r) for r in await recent_runs(session, component, limit=limit)]


@router.get("/storage", response_model=StorageView)
async def get_storage(session: AsyncSession = Depends(get_session)) -> StorageView:
    """Storage usage: media by status/disposition + bytes, and headline totals."""
    return await aq.storage(session)


@router.get("/system", response_model=SystemView)
async def get_system(session: AsyncSession = Depends(get_session)) -> SystemView:
    """System status + pipeline throughput metrics."""
    r = redislib.from_url(get_settings().redis_url)
    try:
        queue_depth = int(await asyncio.to_thread(r.llen, QUEUE_KEY))
    except Exception:
        queue_depth = 0
    finally:
        await asyncio.to_thread(r.close)
    return await aq.system(session, get_settings().environment, queue_depth=queue_depth)


# ── System-health monitoring (component probes + resource metrics) ─────────────────────────


@router.get("/health", response_model=HealthTreeView)
async def get_health(session: AsyncSession = Depends(get_session)) -> HealthTreeView:
    """Full health tree: every component grouped by plane (live-probe + run health) + host
    resource gauges + per-plane/system rollup levels. The System Health dashboard's source."""
    now = datetime.now(UTC)
    values = await aq.all_config_values(session)
    return await aq.health_tree(session, now, values)


@router.get("/metrics/host", response_model=HostMetricsView)
async def get_host_metrics(session: AsyncSession = Depends(get_session)) -> HostMetricsView:
    """Latest host resource utilization (disk/memory/CPU/load)."""
    return await aq.host_metrics(session)


@router.get("/components/{component_id}/metrics", response_model=list[MetricSeries])
async def component_metrics(
    component_id: str,
    metric: str | None = Query(default=None, description="filter to one metric name"),
    window: int = Query(default=3600, ge=60, le=2_592_000, description="lookback seconds"),
    session: AsyncSession = Depends(get_session),
) -> list[MetricSeries]:
    """Resource time-series for one component over a window (one series per metric)."""
    if registry.get(component_id) is None and component_id != "host":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown component")
    return await aq.metric_series(session, component_id, metric, window)


# ── Logs + runtime log-level control ───────────────────────────────────────────────────────


@router.get("/components/{component_id}/logs", response_model=list[LogRecordView])
async def component_logs(
    component_id: str,
    level: str | None = Query(default=None, description="WARNING | ERROR | CRITICAL"),
    q: str | None = Query(default=None, description="substring match on the message"),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[LogRecordView]:
    """Persisted WARNING+ log records for one component (durable, searchable slice of stdout)."""
    if registry.get(component_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown component")
    return await aq.query_logs(session, component_id=component_id, level=level, q=q, limit=limit)


@router.get("/logs/tail/{component_id}")
async def logs_tail(
    component_id: str,
    tail: int = Query(default=200, ge=1, le=2000),
) -> dict:
    """Live tail of a component container's stdout/stderr via the Docker API (full firehose)."""
    m = registry.get(component_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown component")
    if not m.container:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "component has no container")
    text = await docker_api.container_logs(m.container, tail=tail)
    if text is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "docker logs unavailable")
    return {"component": component_id, "container": m.container, "logs": text}


@router.get("/components/{component_id}/log-level", response_model=LogLevelView)
async def get_log_level(
    component_id: str, session: AsyncSession = Depends(get_session)
) -> LogLevelView:
    """A component's runtime log level + whether it is directly controllable."""
    if registry.get(component_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown component")
    values = await aq.all_config_values(session)
    return aq.log_level_view(component_id, values)


@router.put("/components/{component_id}/log-level", response_model=LogLevelView)
async def set_log_level(
    component_id: str,
    body: LogLevelUpdate,
    actor: str = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> LogLevelView:
    """Set a process component's runtime log level (audited; applied within a refresh cycle)."""
    values = await aq.all_config_values(session)
    view = aq.log_level_view(component_id, values)
    if not view.key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            view.note or "log level not directly controllable")
    ok, err = validate_value(view.key, body.level)
    if not ok:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, err or "invalid level")
    spec = SPEC_BY_KEY.get(view.key)
    await config_service.set_value(
        session, view.key, body.level, scope=spec.scope if spec else "logging",
        note=f"{actor}:log-level",
    )
    values = await aq.all_config_values(session)
    return aq.log_level_view(component_id, values)


# ── SSE constants ─────────────────────────────────────────────────────────────
_OVERVIEW_EVERY = 4   # emit a full overview every N ticks
_TICK_SECS = 5        # seconds between polls


def _sse(event: str, data: dict) -> str:
    """Format a single Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/stream")
async def admin_stream(
    request: Request,
    actor: str = Depends(require_admin),
) -> StreamingResponse:
    """Server-Sent Events feed for the Admin Portal.

    Pushes two event types so the portal can update without polling:
    - ``overview`` — full overview snapshot (component health + counts + recent runs)
    - ``run``      — a single agent-run row that changed status since the last tick

    The client reconnects automatically on drop; the stream restarts clean (stateless).
    """
    async def gen():
        seen_runs: dict[str, str] = {}  # run_id → last-seen status
        tick = 0
        try:
            while not await request.is_disconnected():
                async with session_scope() as session:
                    runs = await recent_runs(session, limit=50)

                    # Emit 'run' events for new or status-changed runs.
                    for r in runs:
                        rid = str(r.id)
                        if seen_runs.get(rid) != r.status:
                            seen_runs[rid] = r.status
                            yield _sse("run", aq._run_view(r).model_dump())

                    # Emit full overview every OVERVIEW_EVERY ticks (~20 s).
                    if tick % _OVERVIEW_EVERY == 0:
                        now = datetime.now(UTC)
                        values = await aq.all_config_values(session)
                        components = [
                            await aq.component_view(session, m, now, values)
                            for m in registry.REGISTRY
                        ]
                        overview = OverviewView(
                            components=components,
                            counts=await aq.counts(session),
                            recent_runs=[aq._run_view(r) for r in runs[:15]],
                        )
                        yield _sse("overview", overview.model_dump())

                tick += 1
                await asyncio.sleep(_TICK_SECS)
        except asyncio.CancelledError:
            pass  # client disconnected
        except Exception:
            log.exception("admin SSE stream error")

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/users")
async def list_users() -> dict:
    """User administration lands with Phase 4 auth (no users table yet)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "user management arrives in Phase 4")
