"""Social graph + activity log + generic promotes (Phase 4-B, ADR-0025/0027/0028).

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-21

Three tables build the engagement layer the feed/rec slice needs:

- ``follows`` (data-model §3.5) — a generic follow edge: a user follows a *user*, *entity*,
  or *event*. PK on the (user_id, target_type, target_id) triple. Powers the Following feed.
- ``activity_log`` (ADR-0028) — every meaningful action (view/watch/like/comment/promote/
  follow/upload) with a weight, indexed by (user, created_at). The substrate for the decayed
  interest profile + analytics.
- ``promotes`` (ADR-0025 §2 extended) — a generic up/down promote vote on an *event*,
  *relation* (link), *source*, or *entity* (actor). Event reactions/source_votes (0005)
  stay as they are; this adds the missing **link** and **actor** promote targets (and an
  event/source promote axis distinct from emotion reactions) under one small table.

Like the 0005 interaction tables, ``user_id`` is a plain ``uuid`` with no FK to ``users``
(the GDPR purge fans out explicitly in chronos_core.accounts_repo). ``target_id`` is a plain
``uuid`` (polymorphic across event/relation/source/entity), so no FK either. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # User-uploaded events land in a 'pending' moderation state (ADR-0029). Add the enum value
    # so chronos_core.upload can stamp it (idempotent; PG12+ allows ADD VALUE in a txn).
    op.execute("ALTER TYPE event_status ADD VALUE IF NOT EXISTS 'pending'")

    op.create_table(
        "follows",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),  # no FK (see 0005/0006)
        sa.Column("target_type", sa.String(16), primary_key=True),  # user|entity|event
        sa.Column("target_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Reverse lookups: "who follows X" (followers) + "what does U follow" (following).
    op.create_index("ix_follows_target", "follows", ["target_type", "target_id"])
    op.create_index("ix_follows_user", "follows", ["user_id"])

    op.create_table(
        "activity_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),  # no FK (see 0005/0006)
        sa.Column("kind", sa.String(24), nullable=False),  # view|watch|like|comment|promote|follow|upload|dwell
        sa.Column("target_type", sa.String(16), nullable=False),  # event|entity|source|relation
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_activity_user_created", "activity_log", ["user_id", "created_at"])
    op.create_index("ix_activity_target", "activity_log", ["target_type", "target_id"])

    op.create_table(
        "promotes",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),  # no FK (see 0005/0006)
        sa.Column("target_type", sa.String(16), primary_key=True),  # event|relation|source|entity
        sa.Column("target_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("value", sa.SmallInteger(), nullable=False),  # +1 promote / -1 demote
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_promotes_target", "promotes", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_promotes_target", table_name="promotes")
    op.drop_table("promotes")
    op.drop_index("ix_activity_target", table_name="activity_log")
    op.drop_index("ix_activity_user_created", table_name="activity_log")
    op.drop_table("activity_log")
    op.drop_index("ix_follows_user", table_name="follows")
    op.drop_index("ix_follows_target", table_name="follows")
    op.drop_table("follows")
