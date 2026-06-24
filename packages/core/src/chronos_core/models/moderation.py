"""Moderation flags — the admin approvals queue substrate.

An LLM (or, later, a user report) raises a flag on an event or comment. ``status`` is ``open``
until an admin ``approve``s (clears it; if the item was held, un-holds it) or ``remove``s the
content. The admin badge counts ``status='open'`` flags.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import UuidPk

MODERATION_TARGETS = ("event", "comment")
MODERATION_STATUSES = ("open", "approved", "removed")


class ModerationFlag(UuidPk, Base):
    """A flag raised on a moderatable target (event|comment)."""

    __tablename__ = "moderation_flags"

    target_type: Mapped[str] = mapped_column(String(16), nullable=False)  # event|comment
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="llm", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        Index("ix_moderation_status", "status"),
        Index("ix_moderation_target", "target_type", "target_id"),
    )
