"""Admin Portal DTOs. The portal renders from these generic shapes (component + health +
config-spec), so new backend components surface without new response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthView(BaseModel):
    """Health for one component — run-derived (agents) or probe-derived (infra/services).

    ``status`` keeps its run vocabulary for run-backed components; probe-backed components
    report ok | down | degraded | unknown. ``level`` is an orthogonal severity the UI colours
    by (mirrors status until thresholds land in Phase C)."""

    status: str                       # never|running|ok|stale|error  OR  ok|down|degraded|unknown
    level: str = "ok"                 # ok | warning | degraded | critical
    message: str | None = None        # probe detail (e.g. "connection refused")
    last_run_at: datetime | None = None  # last run (runs) or checked_at (probe)
    last_status: str | None = None
    runs: int = 0
    success_rate: float | None = None


class ComponentView(BaseModel):
    """A managed component: its manifest + current enabled state + health."""

    id: str
    kind: str
    title: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    config_prefix: str | None = None
    enabled: bool | None = None       # None = not toggleable
    health: HealthView
    plane: str | None = None          # edge | api | processing | store | client (UI grouping)
    latest_metrics: dict | None = None  # latest probe/resource metrics snapshot
    doc: str | None = None


class RunView(BaseModel):
    """One agent execution."""

    id: uuid.UUID
    component_id: str
    command: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    stats: dict | None = None
    error: str | None = None


class ConfigEntry(BaseModel):
    """A config key: its spec metadata + current value (secrets masked)."""

    key: str
    type: str
    scope: str
    label: str
    help: str = ""
    component_id: str | None = None
    value: Any = None
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] | None = None
    secret: bool = False


class ConfigUpdate(BaseModel):
    """Write payload for a config key."""

    value: Any


class ComponentDetail(ComponentView):
    """Component view + its config entries + recent runs."""

    config: list[ConfigEntry] = Field(default_factory=list)
    recent_runs: list[RunView] = Field(default_factory=list)


class OverviewView(BaseModel):
    """The admin landing summary: component health + key counts + recent activity."""

    components: list[ComponentView] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    recent_runs: list[RunView] = Field(default_factory=list)


class IntegrityView(BaseModel):
    """Data-integrity counts: published events missing a required field (ADR-0020).

    Every event should carry Time + Location + Actors; these count the shortfalls so the
    geocoder/enricher can consume the worklist and operators can see coverage."""

    published: int = 0                 # total published events
    missing_location: int = 0          # geom IS NULL
    missing_actors: int = 0            # no actor-role entity
    missing_media: int = 0             # no linked media (text-only; ADR-0023)


class StorageView(BaseModel):
    """Storage usage: media by status/disposition + bytes, and event/source totals."""

    media_by_status: dict[str, int] = Field(default_factory=dict)
    media_by_disposition: dict[str, int] = Field(default_factory=dict)
    media_stored_bytes: int = 0
    totals: dict[str, int] = Field(default_factory=dict)
    integrity: "IntegrityView | None" = None  # event Time/Location/Actors coverage (ADR-0020)


class HostMetricsView(BaseModel):
    """Latest host resource utilization snapshot (the gauges atop the Health dashboard)."""

    metrics: dict[str, float] = Field(default_factory=dict)  # disk/mem/cpu/load latest values
    updated_at: datetime | None = None


class PlaneGroup(BaseModel):
    """Components sharing a plane (UI section), with the plane's worst-case rollup level."""

    plane: str                        # edge | api | processing | store | client
    level: str = "ok"                 # worst level across the group's components
    components: list[ComponentView] = Field(default_factory=list)


class HealthTreeView(BaseModel):
    """The System Health dashboard payload: components grouped by plane + host gauges."""

    planes: list[PlaneGroup] = Field(default_factory=list)
    host: HostMetricsView = Field(default_factory=HostMetricsView)
    level: str = "ok"                 # worst level across the whole system
    generated_at: datetime | None = None


class MetricPoint(BaseModel):
    """One time-series sample."""

    ts: datetime
    value: float


class MetricSeries(BaseModel):
    """A component's readings for one metric over a time window (chart/sparkline source)."""

    component_id: str
    metric: str
    unit: str | None = None
    points: list[MetricPoint] = Field(default_factory=list)


class SystemView(BaseModel):
    """System status + pipeline throughput metrics for the Admin Portal."""

    environment: str
    database: str                     # ok | error
    config_keys: int
    components: int
    running_agents: int
    queue_depth: int = 0              # jobs waiting in the Redis run queue
    events_last_hour: int = 0         # events created in the past 60 min
    runs_last_hour: int = 0           # agent runs completed (ok) in the past 60 min
