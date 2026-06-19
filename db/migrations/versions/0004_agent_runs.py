"""Admin Portal foundation: per-execution agent run history.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-19

``agent_runs`` records each agent execution (status + result counts + errors). The Admin
Portal derives agent health/throughput/lag from recent rows (chronos_core.domain.health)
and shows "what is running now" from rows still in status ``running``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("component_id", sa.String(64), nullable=False),
        sa.Column("command", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'running'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("stats", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_agent_runs_component_started", "agent_runs", ["component_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_component_started", table_name="agent_runs")
    op.drop_table("agent_runs")
