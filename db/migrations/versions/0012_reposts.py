"""Reposts — a user re-shares another user's clip to their followers (feed rail "Repost").

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-24

One table backing the feed's Share→"Repost" affordance: a user reposts an event so it surfaces
in *their* followers' "Following" feed and on their own profile. PK on (user_id, event_id) →
at most one repost per event. Unlike ``bookmarks`` a repost is a *public* re-share, so the
action is additionally recorded in ``activity_log`` (kind='share') by the repo caller.

Like the other interaction tables, ``user_id``/``event_id`` are plain ``uuid`` columns with
**no FK** (the GDPR purge fans out explicitly in chronos_core.accounts_repo). Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reposts",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),  # no FK (see 0008)
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # "a user's reposts, newest first" — the profile Reposts tab read pattern.
    op.create_index("ix_reposts_user_created", "reposts", ["user_id", "created_at"])
    # "who reposted this event" — the Following-feed EXISTS + the per-event count.
    op.create_index("ix_reposts_event", "reposts", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_reposts_event", table_name="reposts")
    op.drop_index("ix_reposts_user_created", table_name="reposts")
    op.drop_table("reposts")
