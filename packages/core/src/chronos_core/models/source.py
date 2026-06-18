"""Source + EventSource ORM models — provenance + corroboration.

The count of distinct sources on an event feeds the corroboration component of severity
(see chronos_core.domain.severity).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import Timestamps, UuidPk


class Source(UuidPk, Timestamps, Base):
    """An external source (news article, dataset, encyclopedia entry, primary doc)."""

    __tablename__ = "sources"

    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    snapshot_key: Mapped[str | None] = mapped_column(Text)  # object-store key (archival)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    quality_score: Mapped[int] = mapped_column(SmallInteger, default=50, nullable=False)
    kind: Mapped[str | None] = mapped_column(String(32))  # news|dataset|encyclopedia|...

    __table_args__ = (UniqueConstraint("content_hash", name="uq_sources_content_hash"),)


class EventSource(Base):
    """Link table: which sources attest an event (many-to-many)."""

    __tablename__ = "event_sources"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(String(32), default="reports", nullable=False)
    added_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
