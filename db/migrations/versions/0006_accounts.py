"""Accounts: users, user_identities, user_agreements (ADR-0026, data-model §3.5).

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-21

Real accounts for Phase-4 auth. Multi-provider social login auto-provisions a ``users`` row
and links the identity in ``user_identities`` (account linkage via UNIQUE(provider,sub));
``user_agreements`` records versioned Terms acceptance gating interaction.

The interaction tables (0005) and ``event_relations.created_by`` keep their plain
``user_id``/``created_by`` columns — no FK is back-filled here, so the slices stay decoupled
and GDPR purge fans out explicitly (chronos_core.accounts_repo.purge_user). Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("handle", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128)),
        sa.Column("email", sa.String(320)),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reputation", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("prefs", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("handle", name="uq_users_handle"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "user_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_sub", name="uq_user_identities_provider_sub"),
    )
    op.create_index("ix_user_identities_user", "user_identities", ["user_id"])

    op.create_table(
        "user_agreements",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.String(32), primary_key=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_agreements")
    op.drop_index("ix_user_identities_user", table_name="user_identities")
    op.drop_table("user_identities")
    op.drop_table("users")
