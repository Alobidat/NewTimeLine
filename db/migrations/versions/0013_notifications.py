"""Notifications — in-app activity notifications (Phase 5: the system reaches out).

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-24

One table for the bell/notifications inbox: a recipient is notified when someone **follows**
them, or **likes / comments / replies / reposts** their content. Generated synchronously by the
interaction routers (skip self-actions; agent-curated content has no recipient).

``recipient_id``/``actor_id`` are plain ``uuid`` columns with **no FK** (the GDPR purge fans out
explicitly in chronos_core.accounts_repo, consistent with the other interaction tables).
Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),  # no FK (see 0008)
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),  # follow|like|comment|reply|repost
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),  # context, if any
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    # "my notifications, newest first" + a partial index for the unread badge count.
    op.create_index("ix_notifications_recipient_created", "notifications",
                    ["recipient_id", "created_at"])
    op.create_index("ix_notifications_unread", "notifications", ["recipient_id"],
                    postgresql_where=sa.text("read = false"))


def downgrade() -> None:
    op.drop_index("ix_notifications_unread", table_name="notifications")
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_table("notifications")
