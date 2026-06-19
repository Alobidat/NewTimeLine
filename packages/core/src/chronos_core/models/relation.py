"""EventRelation ORM model — the directed history graph.

A relation points ``src_event`` → ``dst_event`` with a ``kind`` and a ``weight``. The
convention (so traversal has a consistent direction): **src is the earlier/cause, dst is
the later/effect**. "What led to X" = relations where ``dst_event = X``; "what X caused" =
relations where ``src_event = X``. See chronos_agents.relate and docs/data-model.md §3.4.
"""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base


class EventRelation(Base):
    """A directed, weighted edge between two events."""

    __tablename__ = "event_relations"

    src_event: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    dst_event: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    # causal|precursor|same-place|same-actor|thematic|sequel
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_event_relations_dst", "dst_event"),)
