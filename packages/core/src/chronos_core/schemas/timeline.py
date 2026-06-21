"""API DTOs for timeline windows + buckets.

Zoomed-in requests return individual events; zoomed-out requests return aggregated buckets
(count + peak severity per numeric-year bucket) so the client never holds millions of
points. See docs/architecture.md §4.2 and docs/timeline-ux.md §2.3.
"""

import uuid

from pydantic import BaseModel, Field

from chronos_core.models.enums import TimePrecision
from chronos_core.schemas.entity import EntityRead
from chronos_core.schemas.event import EventRead
from chronos_core.schemas.geo import GeoPoint


class TimelineBucket(BaseModel):
    """Aggregated slice of the timeline for zoomed-out rendering (the 'heatline')."""

    t_start: float  # bucket start (year)
    t_end: float  # bucket end (year)
    count: int
    peak_severity: int


class TimelineResponse(BaseModel):
    """Either ``events`` (zoomed in) or ``buckets`` (zoomed out), never both."""

    mode: str  # "events" | "buckets"
    t0: float
    t1: float
    bucket_years: float | None = None  # set when mode == "buckets"
    events: list[EventRead] = Field(default_factory=list)
    buckets: list[TimelineBucket] = Field(default_factory=list)


class SummaryPlace(BaseModel):
    """A place (free-text ``geo_label``) with the event count + a representative point.

    Drives which countries the client draws as silhouettes and where to anchor labels."""

    label: str
    count: int
    lat: float | None = None
    lon: float | None = None


class SummaryRep(BaseModel):
    """A representative event for a timeframe montage — lightweight on purpose.

    Carries only what a collage tile + headline needs (no body/sources/full media)."""

    id: uuid.UUID
    title: str
    t_start: float
    time_precision: TimePrecision
    severity: int
    geo: GeoPoint | None = None
    geo_label: str | None = None
    hero_media_id: uuid.UUID | None = None


class TimelineSummary(BaseModel):
    """Bandwidth-safe distillation of a whole timeframe (many events → one view).

    The payload size is bounded regardless of how many events fall in the window: a fixed
    set of buckets + a capped list of top entities/places/representatives. This is the
    "collapse many events into a summary" surface behind the semantic-zoom timeline."""

    t0: float
    t1: float
    total: int  # events matched in the window (may be far larger than what we return)
    bucket_years: float | None = None
    buckets: list[TimelineBucket] = Field(default_factory=list)
    top_entities: list[EntityRead] = Field(default_factory=list)
    top_places: list[SummaryPlace] = Field(default_factory=list)
    representatives: list[SummaryRep] = Field(default_factory=list)
