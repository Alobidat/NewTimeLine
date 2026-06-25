"""events.chain_built_at — marks events the smart causal-linker has processed.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-25

The Tier-2 smart relation linker (chronos_agents.relate_smart) builds the back-and-forth
history *chain* (precursor/causal/sequel edges) using embeddings + an LLM. This nullable
timestamp lets it pick un-processed events (``chain_built_at IS NULL``) and converge through
the backlog one batch at a time rather than re-LLM-ing the same events every run. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("chain_built_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index for the agent's "next un-processed, important first" pick.
    op.create_index(
        "ix_events_chain_unbuilt", "events", ["severity"],
        postgresql_where=sa.text("chain_built_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_events_chain_unbuilt", table_name="events")
    op.drop_column("events", "chain_built_at")
