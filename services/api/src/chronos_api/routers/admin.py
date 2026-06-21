"""Admin API — the control plane the Admin Portal renders from (ADR-0019).

Generic, manifest/spec-driven endpoints (every call gated by ``require_admin`` and config
writes audited via the Config Service): system overview, component health + control,
schema-driven config read/write, run history, storage, and system status. New backend
components appear here automatically by registering a manifest + config specs — no new
routes needed.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import redis as redislib
from chronos_core import config_service, registry
from chronos_core.config_spec import SPEC_BY_KEY, validate_value
from chronos_core.run_queue import push_job
from chronos_core.runs import recent_runs
from chronos_core.schemas.admin import (
    ComponentDetail,
    ComponentView,
    ConfigEntry,
    ConfigUpdate,
    OverviewView,
    RunView,
    StorageView,
    SystemView,
)
from chronos_core.settings import get_settings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api import admin_queries as aq
from chronos_api.deps import get_session, require_admin

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
    """Coarse system status (resource dashboards expand this later)."""
    return await aq.system(session, get_settings().environment)


@router.get("/users")
async def list_users() -> dict:
    """User administration lands with Phase 4 auth (no users table yet)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "user management arrives in Phase 4")
