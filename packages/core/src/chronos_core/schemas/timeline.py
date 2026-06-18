"""API DTOs for timeline windows + buckets.

Zoomed-in requests return individual events; zoomed-out requests return aggregated buckets
(count + peak severity per numeric-year bucket) so the client never holds millions of
points. See docs/architecture.md §4.2 and docs/timeline-ux.md §2.3.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chronos_core.schemas.event import EventRead


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
