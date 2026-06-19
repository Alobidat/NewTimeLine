"""Phase-3b schema: the entity-anchored history graph + rich media.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-19

Adds the tables behind the product's core promise — search for a place/actor/event and
dig back-and-forth through what *led to* it and what it *caused*:

- ``entities`` + ``event_entities`` — people/orgs/places/topics tagged on events with a
  role (actor | location | subject | affected …). The "US ↔ Iran" anchoring lives here.
- ``event_relations`` — the directed history graph (causal | precursor | same-place |
  same-actor | thematic | sequel), src → dst, weighted.
- ``media`` + ``event_media`` — images/video/clips for rich event detail, stored in the
  object store (``storage_key``) or referenced as an external embed; the link table lets
  the same media attach to several related events and accept links added later by users
  or new sources (see ADR-0017).

Kinds/roles are plain text (like ``sources.kind`` / ``event_sources.relation``) so new
values need no migration. ``pg_trgm`` (enabled in 0001) backs fuzzy title/name search.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    uuid_pk = sa.text("gen_random_uuid()")
    now = sa.text("now()")

    # --- entities (people / orgs / places / topics) -----------------------------------
    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=uuid_pk),
        sa.Column("kind", sa.String(32), nullable=False),  # person|org|place|topic
        sa.Column("name", sa.Text(), nullable=False),
        # normalized (lower/trimmed) name → resolution key when no external_id is known.
        sa.Column("name_key", sa.String(255), nullable=False),
        sa.Column("external_id", sa.String(64)),  # e.g. Wikidata QID
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=False)),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("meta", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.UniqueConstraint("kind", "external_id", name="uq_entities_kind_external_id"),
        sa.UniqueConstraint("kind", "name_key", name="uq_entities_kind_name_key"),
    )
    op.create_index("ix_entities_kind", "entities", ["kind"])
    op.create_index("ix_entities_geom", "entities", ["geom"], postgresql_using="gist")
    op.create_index(
        "ix_entities_name_trgm", "entities", ["name"],
        postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "event_entities",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role", sa.String(32), primary_key=True),  # actor|location|subject|affected
        sa.Column("added_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name="fk_event_entities_event", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], name="fk_event_entities_entity", ondelete="CASCADE"),
    )
    op.create_index("ix_event_entities_entity", "event_entities", ["entity_id"])

    # --- event_relations (the directed history graph) ---------------------------------
    op.create_table(
        "event_relations",
        sa.Column("src_event", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dst_event", postgresql.UUID(as_uuid=True), primary_key=True),
        # causal|precursor|same-place|same-actor|thematic|sequel
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.ForeignKeyConstraint(["src_event"], ["events.id"], name="fk_event_relations_src", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dst_event"], ["events.id"], name="fk_event_relations_dst", ondelete="CASCADE"),
    )
    op.create_index("ix_event_relations_dst", "event_relations", ["dst_event"])

    # --- media + event_media (rich content; ADR-0017) ---------------------------------
    op.create_table(
        "media",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=uuid_pk),
        sa.Column("kind", sa.String(16), nullable=False),  # image|video|audio|embed
        sa.Column("storage_key", sa.Text()),    # object-store key of the stored binary
        sa.Column("source_url", sa.Text()),     # where we found/fetched it
        sa.Column("embed_url", sa.Text()),       # external player URL (e.g. YouTube) when not stored
        sa.Column("thumbnail_key", sa.Text()),   # object-store key of a generated thumbnail
        sa.Column("mime", sa.String(128)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("duration_s", sa.Integer()),   # for video/audio
        sa.Column("bytes", sa.BigInteger()),
        sa.Column("content_hash", sa.String(64)),  # dedup identical binaries
        sa.Column("caption", sa.Text()),
        sa.Column("credit", sa.Text()),          # attribution / rights holder
        sa.Column("license", sa.String(64)),
        # pending=queued for fetch, stored=in object store, external=embed-only, failed
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("added_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.UniqueConstraint("content_hash", name="uq_media_content_hash"),
    )

    op.create_table(
        "event_media",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False, server_default=sa.text("'gallery'")),  # hero|gallery|inline|related
        sa.Column("rank", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("added_by", sa.String(64)),  # agent run OR user id (user-added links)
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name="fk_event_media_event", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], name="fk_event_media_media", ondelete="CASCADE"),
    )
    op.create_index("ix_event_media_media", "event_media", ["media_id"])

    # Fuzzy title search for the new /search endpoint (entity search uses ix_entities_name_trgm).
    op.create_index(
        "ix_events_title_trgm", "events", ["title"],
        postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_events_title_trgm", table_name="events")
    op.drop_index("ix_event_media_media", table_name="event_media")
    op.drop_table("event_media")
    op.drop_table("media")
    op.drop_index("ix_event_relations_dst", table_name="event_relations")
    op.drop_table("event_relations")
    op.drop_index("ix_event_entities_entity", table_name="event_entities")
    op.drop_table("event_entities")
    op.drop_index("ix_entities_name_trgm", table_name="entities")
    op.drop_index("ix_entities_geom", table_name="entities")
    op.drop_index("ix_entities_kind", table_name="entities")
    op.drop_table("entities")
