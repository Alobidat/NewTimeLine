"""LogRecord ORM model — a bounded ring buffer of WARNING+ log lines.

The ``DbRingBufferHandler`` (chronos_core.logging_setup) persists warning/error/critical log
records from every process so an operator can read them in the Admin Portal without shelling
into containers. Bounded by retention (``monitoring.log_retention_days``) + row cap
(``monitoring.log_buffer_max_rows``), pruned in the collector ticker. Full stdout is tailed
on-demand via the Docker API; this table is the durable, searchable WARN+ slice.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import UuidPk


class LogRecord(UuidPk, Base):
    """One persisted log line (WARNING or above)."""

    __tablename__ = "log_record"

    component_id: Mapped[str | None] = mapped_column(String(64))  # mapped from logger name
    logger: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "chronos.api.search"
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # WARNING | ERROR | CRITICAL
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fields: Mapped[dict | None] = mapped_column(JSONB)  # extra structured context
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_log_record_ts", "ts"),
        Index("ix_log_record_component_ts", "component_id", "ts"),
        Index("ix_log_record_level_ts", "level", "ts"),
    )
