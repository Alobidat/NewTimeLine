"""Event + EventReference ORM models — the heart of the timeline.

Time is a signed numeric year (``t_start``/``t_end``); see docs/data-model.md §1 and
chronos_core.domain.temporal. ``t_end`` is materialized at write time so timeline-overlap
queries are a plain indexable range test.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chronos_core.db.base import Base
from chronos_core.models.enums import (
    EventStatus,
    EventVisibility,
    TimePrecision,
    pg_enum,
)
from chronos_core.models.mixins import Timestamps, UuidPk

# Embedding dimension placeholder (Phase 3 fills the column). Keep configurable.
EMBEDDING_DIM = 1024

_precision_enum = pg_enum(TimePrecision, "time_precision")
_status_enum = pg_enum(EventStatus, "event_status")
_visibility_enum = pg_enum(EventVisibility, "event_visibility")


class Event(UuidPk, Timestamps, Base):
    """A canonical event positioned on the main timeline at its anchor time."""

    __tablename__ = "events"

    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)

    # Canonical signed-year span (deep-time capable). t_end is always materialized.
    t_start: Mapped[float] = mapped_column(Float, nullable=False)
    t_end: Mapped[float] = mapped_column(Float, nullable=False)
    time_precision: Mapped[TimePrecision] = mapped_column(
        _precision_enum, nullable=False, default=TimePrecision.DAY
    )
    # Exact modern instant (only when precision is fine + within range); for display/order.
    instant: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    category: Mapped[str | None] = mapped_column(String(64))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)

    severity: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    severity_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False)
    )
    geo_label: Mapped[str | None] = mapped_column(Text)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    status: Mapped[EventStatus] = mapped_column(
        _status_enum, nullable=False, default=EventStatus.PUBLISHED
    )
    # Per-post audience (user uploads); agent/seed/bot events are PUBLIC by construction.
    visibility: Mapped[EventVisibility] = mapped_column(
        _visibility_enum, nullable=False, default=EventVisibility.PUBLIC
    )
    merged_into: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL")
    )
    created_by_agent: Mapped[str | None] = mapped_column(String(64))

    references: Mapped[list[EventReference]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        foreign_keys="EventReference.event_id",
    )

    __table_args__ = (
        Index("ix_events_t_start", "t_start"),
        Index("ix_events_t_end", "t_end"),
        Index("ix_events_category", "category"),
        Index("ix_events_severity", "severity"),
        Index("ix_events_tags", "tags", postgresql_using="gin"),
        Index("ix_events_geom", "geom", postgresql_using="gist"),
    )


class EventReference(UuidPk, Timestamps, Base):
    """A deep-time *subject* an event discusses → populates the event's sub-timeline.

    May link to a canonical event (``subject_event_id``) for recursive sub-timelines.
    """

    __tablename__ = "event_references"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)

    t_start: Mapped[float] = mapped_column(Float, nullable=False)
    t_end: Mapped[float] = mapped_column(Float, nullable=False)
    subject_precision: Mapped[TimePrecision] = mapped_column(
        _precision_enum, nullable=False, default=TimePrecision.ERA
    )
    subject_geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False)
    )
    subject_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL")
    )
    detail: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int] = mapped_column(SmallInteger, default=50, nullable=False)
    extracted_by: Mapped[str | None] = mapped_column(String(64))

    event: Mapped[Event] = relationship(
        back_populates="references", foreign_keys=[event_id]
    )

    __table_args__ = (
        Index("ix_event_references_event_id", "event_id"),
        Index("ix_event_references_t_start", "t_start"),
        Index("ix_event_references_geom", "subject_geom", postgresql_using="gist"),
    )
