"""media.edit_spec: Creator-Studio clip edits applied at transcode (Phase 1 — trim/speed).

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-26

A nullable JSONB holding the edit the transcode agent applies when it builds a clip's ``web``
variant — e.g. ``{"trim_start": 1.5, "trim_end": 9.0, "speed": 2.0}``. Null = no edits, which is
every clip until the editor sets one. Additive; reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media", sa.Column("edit_spec", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "edit_spec")
