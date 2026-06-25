"""media_variants: derived web-playable renditions of video clips (Creator Studio Phase 0).

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-25

The transcode agent re-encodes source clips into a web-safe mp4 (H.264/AAC) so every clip
plays cross-browser. Each video gets one ``web`` variant row — either a real re-encode under
its own ``storage_key`` or a passthrough pointing at the original's key when it was already
web-safe. Additive; reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_variants",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True, server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "media_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("rendition", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime", sa.String(128)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("bytes", sa.BigInteger()),
        sa.Column("status", sa.String(16), nullable=False, server_default="stored"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("media_id", "rendition", name="uq_media_variant_rendition"),
    )
    op.create_index("ix_media_variants_media", "media_variants", ["media_id"])


def downgrade() -> None:
    op.drop_index("ix_media_variants_media", table_name="media_variants")
    op.drop_table("media_variants")
