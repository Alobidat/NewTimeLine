"""AgentRun ORM model — one row per agent execution (the "what are they doing / how are
they doing" record the Admin Portal reads).

A row is created ``running`` when an agent starts and updated to ``ok``/``error`` when it
finishes, carrying the agent's own result counts in ``stats``. Health (liveness, lag,
success rate) is *derived* from recent runs by chronos_core.domain.health.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import UuidPk


class AgentRun(UuidPk, Base):
    """A single execution of an agent/command."""

    __tablename__ = "agent_runs"

    component_id: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "agent:enrich"
    command: Mapped[str] = mapped_column(String(64), nullable=False)       # e.g. "enrich"
    # status: running | ok | error
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict | None] = mapped_column(JSONB)   # the agent's result counts
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_agent_runs_component_started", "component_id", "started_at"),)
