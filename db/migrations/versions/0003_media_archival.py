"""Phase-3b media archival: store-vs-link policy fields + per-host availability tracking.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-19

Adds the columns the archival decision engine (ADR-0018, chronos_core.domain.media_policy)
reads/writes, plus ``media_sources`` — every host URL a media item has been seen at, which
is the corroboration signal behind "available at one or more stable sources". Media tends
to vanish under political/government/social pressure, so hot/sensitive items are captured
locally first; durable, corroborated items can be linked or released later.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    now = sa.text("now()")

    op.add_column("media", sa.Column("disposition", sa.String(16), nullable=False, server_default=sa.text("'archive'")))
    op.add_column("media", sa.Column("sensitivity", sa.SmallInteger(), nullable=False, server_default=sa.text("0")))
    op.add_column("media", sa.Column("persistence_confidence", sa.SmallInteger(), nullable=False, server_default=sa.text("0")))
    op.add_column("media", sa.Column("origin_kind", sa.String(32)))
    op.add_column("media", sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("media", sa.Column("last_checked_at", sa.DateTime(timezone=True)))
    op.add_column("media", sa.Column("last_available_at", sa.DateTime(timezone=True)))
    op.add_column("media", sa.Column("avail_state", sa.String(16), nullable=False, server_default=sa.text("'unknown'")))

    op.create_table(
        "media_sources",
        sa.Column("media_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_url", sa.Text(), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("is_stable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("avail_state", sa.String(16), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("last_available_at", sa.DateTime(timezone=True)),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], name="fk_media_sources_media", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_media_sources_source", ondelete="SET NULL"),
    )
    op.create_index("ix_media_sources_media", "media_sources", ["media_id"])


def downgrade() -> None:
    op.drop_index("ix_media_sources_media", table_name="media_sources")
    op.drop_table("media_sources")
    for col in (
        "avail_state", "last_available_at", "last_checked_at", "pinned",
        "origin_kind", "persistence_confidence", "sensitivity", "disposition",
    ):
        op.drop_column("media", col)
