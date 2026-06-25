"""MetricSample ORM model — one resource/utilization data point in the time-series.

The monitoring collector appends rows every tick (per-container CPU/mem/net/blkio pulled
from the Docker Engine API, plus host disk under ``component_id="host"``). The Admin API
reads windows of these for the portal's charts/sparklines. Append-only; pruned by retention
(``monitoring.metric_retention_days``) in the collector ticker.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import UuidPk


class MetricSample(UuidPk, Base):
    """A single (component, metric, value) reading at a point in time."""

    __tablename__ = "metric_sample"

    component_id: Mapped[str] = mapped_column(String(64), nullable=False)  # "service:api" | "host"
    metric: Mapped[str] = mapped_column(String(64), nullable=False)  # "cpu_pct" | "mem_rss_bytes"
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16))  # pct | bytes | count | bytes_per_s
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_metric_sample_component_metric_ts", "component_id", "metric", "ts"),
        Index("ix_metric_sample_ts", "ts"),  # retention prune
    )
