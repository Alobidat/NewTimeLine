"""Rich profiles + friends + per-post privacy + moderation (one schema drop).

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-24

All schema for the "rich profiles + friends + privacy + post delivery + moderation" effort
lands here; the application phases build on it incrementally.

- ``users.bio`` — a free-text profile bio (nullable).
- ``events.visibility`` — per-post audience enum ``public|followers|friends``,
  NOT NULL DEFAULT ``public`` (+ index) so the feed/profile SQL can gate on it. Existing,
  agent, seed and bot events default to ``public`` → zero behaviour change until a user opts
  into a tighter audience.
- **Backfill** ``UPDATE events SET status='published' WHERE status='pending'`` — user uploads
  were stranded in ``pending`` with no moderation/publish path; this one-time publish releases
  them (the new upload flow auto-publishes going forward). Intentional, not auto-reverted.
- ``friendships`` — one row per unordered pair (request/accept), ``status pending|accepted``,
  with a functional unique index on the unordered pair + lookup indexes by each side+status.
- ``moderation_flags`` — the admin approvals queue substrate (LLM/user-sourced flags on
  events/comments), indexed by ``status`` and target.

Privacy *settings* live in ``users.prefs['privacy']`` (JSONB, already present) — no column.
``user_id``/target ids are plain uuids with no FK (the GDPR purge fans out explicitly), except
``moderation_flags`` which carries none. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

event_visibility = postgresql.ENUM(
    "public", "followers", "friends", name="event_visibility", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()

    # --- profiles -------------------------------------------------------------------
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))

    # --- per-post visibility --------------------------------------------------------
    event_visibility.create(bind, checkfirst=True)
    op.add_column(
        "events",
        sa.Column(
            "visibility", event_visibility, nullable=False, server_default=sa.text("'public'")
        ),
    )
    op.create_index("ix_events_visibility", "events", ["visibility"])
    # Release uploads that were stranded in 'pending' (no prior publish path). One-time.
    op.execute("UPDATE events SET status = 'published' WHERE status = 'pending'")

    # --- friendships (request + accept, mutual) -------------------------------------
    op.create_table(
        "friendships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),  # no FK (purge)
        sa.Column("addressee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    # At most one friendship per unordered pair (regardless of who requested).
    op.execute(
        "CREATE UNIQUE INDEX uq_friendship_pair ON friendships "
        "(LEAST(requester_id, addressee_id), GREATEST(requester_id, addressee_id))"
    )
    op.create_index("ix_friendships_addressee", "friendships", ["addressee_id", "status"])
    op.create_index("ix_friendships_requester", "friendships", ["requester_id", "status"])

    # --- moderation flags (admin approvals queue) -----------------------------------
    op.create_table(
        "moderation_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("target_type", sa.String(16), nullable=False),  # event|comment
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default=sa.text("'llm'")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("severity", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'open'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_moderation_status", "moderation_flags", ["status"])
    op.create_index("ix_moderation_target", "moderation_flags", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_moderation_target", table_name="moderation_flags")
    op.drop_index("ix_moderation_status", table_name="moderation_flags")
    op.drop_table("moderation_flags")

    op.drop_index("ix_friendships_requester", table_name="friendships")
    op.drop_index("ix_friendships_addressee", table_name="friendships")
    op.execute("DROP INDEX IF EXISTS uq_friendship_pair")
    op.drop_table("friendships")

    op.drop_index("ix_events_visibility", table_name="events")
    op.drop_column("events", "visibility")
    event_visibility.drop(op.get_bind(), checkfirst=True)

    op.drop_column("users", "bio")
