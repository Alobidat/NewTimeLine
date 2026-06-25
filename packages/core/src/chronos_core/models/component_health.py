"""ComponentHealth ORM model — the latest live-probe snapshot for one component.

The monitoring collector (chronos_core.monitoring) upserts one row per *probe-backed*
component (stores, edge, api, worker) every tick. The Admin API reads these rows so the
portal can show real liveness/degradation for infra that has no ``agent_runs`` (agents keep
deriving health from runs; this complements them — see ADR-0019 / registry.health_source).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base


class ComponentHealth(Base):
    """Latest probe verdict + metrics for one component (natural PK, upserted)."""

    __tablename__ = "component_health"

    component_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. "store:redis"
    # status: ok | down | degraded | unknown  (live probe verdict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    # level: ok | warning | degraded | critical  (severity, from thresholds in Phase C)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    message: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict | None] = mapped_column(JSONB)  # latest probe metrics snapshot
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
