"""monitoring: component_health snapshots + metric_sample time-series + log_record buffer.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-25

Backs the system-health subsystem (ADR-0019 extension): live infra probes write
``component_health``, the resource collector appends ``metric_sample`` (CPU/mem/net/disk),
and the DB ring-buffer logging handler persists WARNING+ lines to ``log_record``. All three
are additive; reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Latest live-probe verdict per component (upserted; natural PK on component_id).
    op.create_table(
        "component_health",
        sa.Column("component_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("level", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("message", sa.Text()),
        sa.Column("metrics", JSONB()),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Resource/utilization time-series (append-only, retention-pruned).
    op.create_table(
        "metric_sample",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True, server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("component_id", sa.String(64), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(16)),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_metric_sample_component_metric_ts", "metric_sample",
        ["component_id", "metric", "ts"],
    )
    op.create_index("ix_metric_sample_ts", "metric_sample", ["ts"])

    # Bounded WARNING+ log ring buffer (durable, searchable slice of stdout).
    op.create_table(
        "log_record",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True, server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("component_id", sa.String(64)),
        sa.Column("logger", sa.String(128), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("fields", JSONB()),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_log_record_ts", "log_record", ["ts"])
    op.create_index("ix_log_record_component_ts", "log_record", ["component_id", "ts"])
    op.create_index("ix_log_record_level_ts", "log_record", ["level", "ts"])


def downgrade() -> None:
    op.drop_index("ix_log_record_level_ts", table_name="log_record")
    op.drop_index("ix_log_record_component_ts", table_name="log_record")
    op.drop_index("ix_log_record_ts", table_name="log_record")
    op.drop_table("log_record")

    op.drop_index("ix_metric_sample_ts", table_name="metric_sample")
    op.drop_index("ix_metric_sample_component_metric_ts", table_name="metric_sample")
    op.drop_table("metric_sample")

    op.drop_table("component_health")
