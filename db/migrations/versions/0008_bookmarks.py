"""Bookmarks — a user's private saved-events collection (Phase 4-B+, social-and-feed §5).

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-21

One table backing the feed's "Bookmark"/"Saved" affordance (FR-1.4 / FR-3.3):

- ``bookmarks`` — a user saves an event. PK on (user_id, event_id) → at most one save per
  event. Unlike ``follows``/``promotes`` a bookmark is private and carries no activity weight,
  so nothing is written to ``activity_log``.

Like the 0005/0007 interaction tables, ``user_id`` and ``event_id`` are plain ``uuid`` columns
with **no FK** (the GDPR purge fans out explicitly in chronos_core.accounts_repo). Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bookmarks",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),  # no FK (see 0005/0007)
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # "the caller's saved events, newest first" — the only read pattern.
    op.create_index("ix_bookmarks_user_created", "bookmarks", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_bookmarks_user_created", table_name="bookmarks")
    op.drop_table("bookmarks")
