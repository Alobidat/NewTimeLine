"""Read/aggregation helpers for the Admin API.

Everything the portal shows is assembled here from three generic sources — the component
**registry** (manifests), the **config specs** (typed config metadata), and **agent_runs**
(health/history) — so new components need no new query code.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from chronos_core import config_service, registry
from chronos_core.config_spec import SPEC_BY_KEY, SPECS, public_value
from chronos_core.domain.health import RunInfo, derive_health
from chronos_core.models.component_health import ComponentHealth
from chronos_core.models.log_record import LogRecord
from chronos_core.registry import ComponentManifest
from chronos_core.runs import recent_runs
from chronos_core.schemas.admin import (
    ComponentView,
    ConfigEntry,
    HealthTreeView,
    HealthView,
    HostMetricsView,
    IntegrityView,
    LogLevelView,
    LogRecordView,
    MetricPoint,
    MetricSeries,
    PlaneGroup,
    RunView,
    StorageView,
    SystemView,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Runtime log-level config key per directly-controllable process component.
_LOG_LEVEL_KEY = {"service:api": "logging.api.level", "service:worker": "logging.worker.level"}
_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]

# Default UI plane per kind when a manifest doesn't declare one explicitly.
_DEFAULT_PLANE = {"agent": "processing", "service": "api", "store": "store"}

# Map run-derived status → severity level (probe components carry their own stored level).
_RUN_LEVEL = {"error": "critical", "stale": "warning"}

# Severity ordering for plane/system rollups (worst wins).
_LEVEL_RANK = {"ok": 0, "warning": 1, "degraded": 2, "critical": 3}
# Stable plane ordering for the dashboard (top → bottom).
_PLANE_ORDER = ["edge", "api", "processing", "store", "client"]


def _worst(levels) -> str:
    """The most severe level in an iterable (defaults to ok)."""
    return max(levels, key=lambda lv: _LEVEL_RANK.get(lv, 0), default="ok")


def _run_view(r) -> RunView:
    return RunView(
        id=r.id, component_id=r.component_id, command=r.command, status=r.status,
        started_at=r.started_at, finished_at=r.finished_at, stats=r.stats, error=r.error,
    )


async def all_config_values(session: AsyncSession) -> dict:
    """Every config value currently set in the DB (key → value)."""
    return await config_service.get_many(session, "")


def config_entries(
    values: dict, *, component_id: str | None = None, scope: str | None = None
) -> list[ConfigEntry]:
    """Build config entries (spec + current value) optionally filtered by component/scope."""
    out: list[ConfigEntry] = []
    for spec in SPECS:
        if component_id is not None and spec.component_id != component_id:
            continue
        if scope is not None and spec.scope != scope:
            continue
        value = values.get(spec.key, spec.default)
        out.append(
            ConfigEntry(
                key=spec.key, type=spec.type, scope=spec.scope, label=spec.label,
                help=spec.help, component_id=spec.component_id,
                value=public_value(spec.key, value), default=spec.default,
                minimum=spec.minimum, maximum=spec.maximum, choices=spec.choices,
                secret=spec.secret,
            )
        )
    return out


async def component_health_view(
    session: AsyncSession, component_id: str, now: datetime
) -> HealthView:
    """Derive a component's health from its recent runs (run-backed components)."""
    runs = await recent_runs(session, component_id, limit=20)
    infos = [RunInfo(r.status, r.started_at, r.finished_at) for r in runs]
    h = derive_health(infos, now)
    return HealthView(level=_RUN_LEVEL.get(h.status, "ok"), **asdict(h))


def _probe_health(row: ComponentHealth | None) -> HealthView:
    """Build a HealthView from a probe snapshot row (placeholder until first probe)."""
    if row is None:
        return HealthView(status="unknown", level="warning", message="awaiting first probe")
    return HealthView(
        status=row.status, level=row.level, message=row.message,
        last_run_at=row.checked_at, last_status=row.status,
    )


async def probe_health_view(session: AsyncSession, component_id: str) -> HealthView:
    """Read a component's latest live-probe snapshot (probe-backed infra/services)."""
    return _probe_health(await session.get(ComponentHealth, component_id))


async def component_view(
    session: AsyncSession, m: ComponentManifest, now: datetime, values: dict
) -> ComponentView:
    """Assemble a component's view (manifest + enabled state + health).

    Health comes from the live-probe snapshot (``health_source="probe"``: infra/services) or
    derived from recent runs (``"runs"``: agents) — see registry.health_source."""
    enabled = values.get(m.enabled_key) if m.enabled_key else None
    latest_metrics = None
    if m.health_source == "probe":
        row = await session.get(ComponentHealth, m.id)
        health = _probe_health(row)
        latest_metrics = row.metrics if row else None
    else:
        health = await component_health_view(session, m.id, now)
    return ComponentView(
        id=m.id, kind=m.kind, title=m.title, description=m.description,
        capabilities=m.capabilities, actions=m.actions, config_prefix=m.config_prefix,
        enabled=enabled, health=health, doc=m.doc,
        plane=m.plane or _DEFAULT_PLANE.get(m.kind), latest_metrics=latest_metrics,
    )


async def counts(session: AsyncSession) -> dict[str, int]:
    """Headline entity counts for the overview."""
    row = (
        await session.execute(
            text(
                "SELECT (SELECT count(*) FROM events) AS events, "
                "(SELECT count(*) FROM entities) AS entities, "
                "(SELECT count(*) FROM event_relations) AS relations, "
                "(SELECT count(*) FROM media) AS media, "
                "(SELECT count(*) FROM sources) AS sources, "
                "(SELECT count(*) FROM moderation_flags WHERE status='open') AS moderation_open"
            )
        )
    ).first()
    return {
        "events": row.events, "entities": row.entities, "relations": row.relations,
        "media": row.media, "sources": row.sources,
        "moderation_open": row.moderation_open,
    }


async def integrity(session: AsyncSession) -> IntegrityView:
    """Count published events missing a required field (Location / Actors / Media) — ADR-0020.

    This is the worklist the geocoder + enricher consume and the coverage the portal shows."""
    row = (
        await session.execute(
            text(
                "SELECT count(*) AS published, "
                "count(*) FILTER (WHERE geom IS NULL) AS missing_location, "
                "count(*) FILTER (WHERE NOT EXISTS ("
                "  SELECT 1 FROM event_entities ee WHERE ee.event_id = e.id "
                "  AND ee.role = 'actor')) AS missing_actors, "
                "count(*) FILTER (WHERE NOT EXISTS ("
                "  SELECT 1 FROM event_media em WHERE em.event_id = e.id)) AS missing_media "
                "FROM events e WHERE e.status = 'published'"
            )
        )
    ).first()
    return IntegrityView(
        published=row.published,
        missing_location=row.missing_location,
        missing_actors=row.missing_actors,
        missing_media=row.missing_media,
    )


async def storage(session: AsyncSession) -> StorageView:
    """Media usage by status/disposition + stored bytes, plus headline totals."""
    by_status = {
        r.status: r.c
        for r in (await session.execute(
            text("SELECT status, count(*) AS c FROM media GROUP BY status")
        )).all()
    }
    by_disp = {
        r.disposition: r.c
        for r in (await session.execute(
            text("SELECT disposition, count(*) AS c FROM media GROUP BY disposition")
        )).all()
    }
    stored_bytes = await session.scalar(
        text("SELECT coalesce(sum(bytes), 0) FROM media WHERE status = 'stored'")
    )
    return StorageView(
        media_by_status=by_status, media_by_disposition=by_disp,
        media_stored_bytes=int(stored_bytes or 0), totals=await counts(session),
        integrity=await integrity(session),
    )


async def system(session: AsyncSession, environment: str, queue_depth: int = 0) -> SystemView:
    """System status + pipeline throughput metrics."""
    running, config_keys, events_1h, runs_1h = (
        await session.scalar(
            text("SELECT count(*) FROM agent_runs WHERE status = 'running'")
        ),
        await session.scalar(text("SELECT count(*) FROM config")),
        await session.scalar(
            text("SELECT count(*) FROM events WHERE created_at > now() - interval '1 hour'")
        ),
        await session.scalar(
            text(
                "SELECT count(*) FROM agent_runs "
                "WHERE status = 'ok' AND finished_at > now() - interval '1 hour'"
            )
        ),
    )
    return SystemView(
        environment=environment, database="ok",
        config_keys=int(config_keys or 0),
        components=len(registry.REGISTRY),
        running_agents=int(running or 0),
        queue_depth=queue_depth,
        events_last_hour=int(events_1h or 0),
        runs_last_hour=int(runs_1h or 0),
    )


# ── Monitoring reads (system-health dashboard) ──────────────────────────────────────────────


async def host_metrics(session: AsyncSession) -> HostMetricsView:
    """Latest value per host metric (DISTINCT ON keeps the newest sample of each)."""
    rows = (await session.execute(text(
        "SELECT DISTINCT ON (metric) metric, value, ts FROM metric_sample "
        "WHERE component_id = 'host' ORDER BY metric, ts DESC"
    ))).all()
    return HostMetricsView(
        metrics={r.metric: float(r.value) for r in rows},
        updated_at=max((r.ts for r in rows), default=None),
    )


async def health_tree(
    session: AsyncSession, now: datetime, values: dict
) -> HealthTreeView:
    """Full health snapshot: every component grouped by plane + host gauges + rollups."""
    views = [await component_view(session, m, now, values) for m in registry.REGISTRY]

    by_plane: dict[str, list[ComponentView]] = {}
    for v in views:
        by_plane.setdefault(v.plane or "other", []).append(v)

    ordered = sorted(by_plane, key=lambda p: (_PLANE_ORDER.index(p) if p in _PLANE_ORDER
                                              else len(_PLANE_ORDER), p))
    groups = [
        PlaneGroup(plane=p, components=by_plane[p],
                   level=_worst(c.health.level for c in by_plane[p]))
        for p in ordered
    ]
    return HealthTreeView(
        planes=groups, host=await host_metrics(session),
        level=_worst(g.level for g in groups), generated_at=now,
    )


async def metric_series(
    session: AsyncSession, component_id: str, metric: str | None, window_seconds: int
) -> list[MetricSeries]:
    """Time-series for a component over a window, one MetricSeries per metric name."""
    sql = (
        "SELECT metric, unit, ts, value FROM metric_sample "
        "WHERE component_id = :cid AND ts > now() - make_interval(secs => :w) "
    )
    params: dict = {"cid": component_id, "w": window_seconds}
    if metric:
        sql += "AND metric = :m "
        params["m"] = metric
    sql += "ORDER BY metric, ts"
    rows = (await session.execute(text(sql), params)).all()

    series: dict[str, MetricSeries] = {}
    for r in rows:
        s = series.get(r.metric)
        if s is None:
            s = series[r.metric] = MetricSeries(
                component_id=component_id, metric=r.metric, unit=r.unit
            )
        s.points.append(MetricPoint(ts=r.ts, value=float(r.value)))
    return list(series.values())


# ── Logs + runtime log levels ───────────────────────────────────────────────────────────────


async def query_logs(
    session: AsyncSession, *, component_id: str | None, level: str | None,
    q: str | None, limit: int,
) -> list[LogRecordView]:
    """Most-recent persisted WARNING+ log records, filtered by component/level/text."""
    stmt = select(LogRecord)
    if component_id:
        stmt = stmt.where(LogRecord.component_id == component_id)
    if level:
        stmt = stmt.where(LogRecord.level == level)
    if q:
        stmt = stmt.where(LogRecord.message.ilike(f"%{q}%"))
    stmt = stmt.order_by(LogRecord.ts.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        LogRecordView(
            id=r.id, component_id=r.component_id, logger=r.logger,
            level=r.level, message=r.message, ts=r.ts,
        )
        for r in rows
    ]


def log_level_view(component_id: str, values: dict) -> LogLevelView:
    """A component's runtime log-level control state (directly controllable for the api +
    worker processes; agents share the worker process's level)."""
    key = _LOG_LEVEL_KEY.get(component_id)
    if key:
        spec = SPEC_BY_KEY.get(key)
        return LogLevelView(
            component_id=component_id, key=key,
            level=values.get(key, spec.default if spec else "INFO"),
            choices=(spec.choices if spec and spec.choices else _LOG_LEVELS),
        )
    m = registry.get(component_id)
    if m and (m.kind == "agent" or m.plane == "processing"):
        wk = _LOG_LEVEL_KEY["service:worker"]
        return LogLevelView(
            component_id=component_id, key=None, level=values.get(wk, "INFO"),
            choices=_LOG_LEVELS, note="Runs in the worker process — set the level on Agent Worker.",
        )
    return LogLevelView(component_id=component_id, key=None, level=None, choices=[],
                        note="No application logger (use container stdout).")
