"""Interaction foundations: comments, reactions, source_votes (ADR-0025).

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-21

The user-engagement substrate designed in docs/data-model.md §3.5–3.7. Writes are gated by
the ``get_actor`` identity stub until Phase-4 OIDC lands.

**users FK choice (deliberate, Phase-4-compatible):** ``user_id`` is a plain ``uuid`` column
with **no FK to a users table**. The accounts system (``users`` / ``user_identities``) is a
Phase-4 deliverable; pulling it in now would balloon this slice. A later migration can add
the FK once ``users`` exists — the column type/name already match data-model.md §3.5.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),  # no FK yet (Phase 4 accounts)
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("comments.id", ondelete="CASCADE")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'visible'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_comments_event_created", "comments", ["event_id", "created_at"])
    op.create_index("ix_comments_parent", "comments", ["parent_id"])

    op.create_table(
        "reactions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),  # no FK yet
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kind", sa.String(16), primary_key=True),  # like|dislike|important|doubt
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reactions_event", "reactions", ["event_id"])

    op.create_table(
        "source_votes",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),  # no FK yet
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("verdict", sa.String(16), nullable=False),  # corroborate|dispute|irrelevant
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_source_votes_event", "source_votes", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_source_votes_event", table_name="source_votes")
    op.drop_table("source_votes")
    op.drop_index("ix_reactions_event", table_name="reactions")
    op.drop_table("reactions")
    op.drop_index("ix_comments_parent", table_name="comments")
    op.drop_index("ix_comments_event_created", table_name="comments")
    op.drop_table("comments")
