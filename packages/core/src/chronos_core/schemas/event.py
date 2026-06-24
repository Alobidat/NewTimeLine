"""API DTOs for events, references, and sources (Pydantic v2).

Shared by the API (responses) and agents (publish payloads). Geometry is exposed as simple
lon/lat for points (Phase 1); richer GeoJSON can be added when polygons land.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from chronos_core.models.enums import EventStatus, TimePrecision
from chronos_core.schemas.entity import EntityRole
from chronos_core.schemas.geo import GeoPoint  # re-exported for existing importers
from chronos_core.schemas.media import MediaRead

__all__ = [
    "GeoPoint",
    "SourceRead",
    "EventReferenceRead",
    "EventRead",
    "EventDetail",
    "EventCreate",
]


class SourceRead(BaseModel):
    """A source attesting an event."""

    id: uuid.UUID
    url: str
    domain: str
    title: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    kind: str | None = None
    quality_score: int


class EventReferenceRead(BaseModel):
    """A subject reference → one item on an event's sub-timeline."""

    id: uuid.UUID
    label: str
    t_start: float
    t_end: float
    subject_precision: TimePrecision
    detail: str | None = None
    confidence: int
    subject_event_id: uuid.UUID | None = None
    geo: GeoPoint | None = None


class EventRead(BaseModel):
    """An event as plotted on the timeline/map (list/window views)."""

    id: uuid.UUID
    title: str
    summary: str | None = None
    t_start: float
    t_end: float
    time_precision: TimePrecision
    instant: datetime | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    severity: int
    confidence: int
    source_count: int
    geo: GeoPoint | None = None
    geo_label: str | None = None
    status: EventStatus
    visibility: str = "public"  # per-post audience (public|followers|friends)
    # The uploading user's id for user-generated clips (origin_kind='user'); None for
    # agent/seed events. Lets the client offer "follow the creator" (target_type='user').
    author_id: uuid.UUID | None = None


class EventDetail(EventRead):
    """Full event view: adds body, sources, sub-timeline references, tagged entities, and
    rich media (images/video clips)."""

    body: str | None = None
    sources: list[SourceRead] = Field(default_factory=list)
    references: list[EventReferenceRead] = Field(default_factory=list)
    entities: list[EntityRole] = Field(default_factory=list)
    media: list[MediaRead] = Field(default_factory=list)


class EventCreate(BaseModel):
    """Publish payload (used by agents/seed). ``t_end`` is materialized server-side if
    omitted, from ``time_precision``."""

    title: str
    summary: str | None = None
    body: str | None = None
    t_start: float
    t_end: float | None = None
    time_precision: TimePrecision = TimePrecision.DAY
    instant: datetime | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    geo: GeoPoint | None = None
    geo_label: str | None = None
    created_by_agent: str | None = None
