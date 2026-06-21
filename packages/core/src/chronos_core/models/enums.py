"""Enumerations shared by ORM models and the DB. TimePrecision is reused from the domain
layer so the value set has a single source of truth."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum

from chronos_core.domain.temporal import TimePrecision  # re-exported single source

__all__ = ["TimePrecision", "EventStatus", "IngestState", "pg_enum"]


def pg_enum(py_enum: type[StrEnum], name: str) -> SAEnum:
    """Build a SQLAlchemy Enum that stores the member *values* (lowercase) as the PG enum
    labels — not the member names (uppercase), which is the SQLAlchemy default. Keeps the
    DB labels matching docs/data-model.md and the hand-written migration.
    """
    return SAEnum(
        py_enum,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        create_type=False,  # types are created explicitly in the migration
    )


class EventStatus(StrEnum):
    """Lifecycle of a canonical event."""

    DRAFT = "draft"
    PUBLISHED = "published"
    MERGED = "merged"
    RETRACTED = "retracted"
    # User-uploaded events land here pending the moderation stub (ADR-0029). Held out of the
    # public feed (which filters status='published') until promoted to PUBLISHED.
    PENDING = "pending"


class IngestState(StrEnum):
    """Processing state of a raw ingested item."""

    NEW = "new"
    NORMALIZED = "normalized"
    PUBLISHED = "published"
    DISCARDED = "discarded"
