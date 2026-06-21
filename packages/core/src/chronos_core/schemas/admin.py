"""Admin Portal DTOs. The portal renders from these generic shapes (component + health +
config-spec), so new backend components surface without new response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthView(BaseModel):
    """Derived health for one component (see chronos_core.domain.health)."""

    status: str                       # never | running | ok | stale | error
    last_run_at: datetime | None = None
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
