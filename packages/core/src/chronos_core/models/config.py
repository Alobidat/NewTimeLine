"""Config + ConfigAudit ORM models — the DB-backed Config Service (ADR-0006).

All agent behavior, budgets, and thresholds are runtime config (versioned + audited), so
operators tune the system without redeploys. See docs/admin-portal.md §2.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import UuidPk


class Config(Base):
    """A single settings row, keyed by dotted path (e.g. ``agents.enricher.model``)."""

    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool] = mapped_column(
        JSONB, nullable=False
    )
    scope: Mapped[str] = mapped_column(String(64), nullable=False)  # global|agent:*|...
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConfigAudit(UuidPk, Base):
    """Append-only audit of every config change (who/what/before→after)."""

    __tablename__ = "config_audit"

    key: Mapped[str] = mapped_column(String(255), nullable=False)
    old_value: Mapped[object | None] = mapped_column(JSONB)
    new_value: Mapped[object | None] = mapped_column(JSONB)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
