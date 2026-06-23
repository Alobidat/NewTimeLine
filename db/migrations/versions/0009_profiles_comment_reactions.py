"""Social profiles + comment reactions (rich comment threads, ADR-0025+).

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-23

Two additions backing richer social conversation:

- ``users.avatar_url`` — the profile picture (the OAuth ``picture`` claim, captured at login).
  Nullable; email-login users have none and the client renders an initials avatar instead.
- ``comment_reactions`` — a user's reaction to a *comment* (the same kind vocabulary as event
  reactions: like|dislike|important|doubt). PK on (user_id, comment_id, kind) → one of each
  kind per user per comment. ``comment_id`` FK cascades so a removed comment drops its
  reactions. ``user_id`` is a plain uuid with no FK (the GDPR purge fans out explicitly).
  Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(1024), nullable=True))

    op.create_table(
        "comment_reactions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),  # no FK (see 0005)
        sa.Column(
            "comment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("kind", sa.String(16), primary_key=True),  # like|dislike|important|doubt
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    # "all reactions for a comment" — the aggregate read pattern.
    op.create_index("ix_comment_reactions_comment", "comment_reactions", ["comment_id"])


def downgrade() -> None:
    op.drop_index("ix_comment_reactions_comment", table_name="comment_reactions")
    op.drop_table("comment_reactions")
    op.drop_column("users", "avatar_url")
