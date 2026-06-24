"""AI users (bot personas): users.is_bot + bot_profiles side table.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-24

Backs the "AI users" feature (autonomous bot personas that post free-licensed videos and
interact). Two additions:

- ``users.is_bot`` — a cheap, indexed predicate marking an account as a bot persona (no join to
  ``bot_profiles`` needed to filter bots in/out of any metric). Backfilled ``false`` for all
  existing accounts.
- ``bot_profiles`` — 1:1 with ``users`` (PK = ``user_id`` FK ON DELETE CASCADE): persona text,
  interests + weights, posting cadence/caps/quality-threshold, enable flags (admin suspend =
  ``enabled=false``), running stats, and the deterministic generation ``seed``.

Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default false so existing rows backfill; then drop it so the model owns the default.
    op.add_column(
        "users",
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_users_is_bot", "users", ["is_bot"])
    op.alter_column("users", "is_bot", server_default=None)

    op.create_table(
        "bot_profiles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("persona", sa.Text()),
        sa.Column("interests", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("interest_weights", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("tone", sa.String(64)),
        sa.Column("post_cadence_min", sa.Integer(), nullable=False, server_default="720"),
        sa.Column("interact_cadence_min", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("quality_threshold", sa.SmallInteger(), nullable=False, server_default="60"),
        sa.Column("daily_post_cap", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("daily_interact_cap", sa.SmallInteger(), nullable=False, server_default="30"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("posts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interacts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_post_at", sa.DateTime(timezone=True)),
        sa.Column("last_interact_at", sa.DateTime(timezone=True)),
        sa.Column("posts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interactions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_bot_profiles_enabled", "bot_profiles", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_bot_profiles_enabled", table_name="bot_profiles")
    op.drop_table("bot_profiles")
    op.drop_index("ix_users_is_bot", table_name="users")
    op.drop_column("users", "is_bot")
