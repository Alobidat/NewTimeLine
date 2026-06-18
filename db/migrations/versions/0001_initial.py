"""Initial Phase-1 schema: events (dual-time) + references + sources + ingest + config.

Revision ID: 0001
Revises:
Create Date: 2026-06-18

Mirrors chronos_core.models. Extensions (postgis/vector/pg_trgm) are ensured here too so
the migration is self-sufficient on any Postgres (the docker image also enables them).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024

# Enum types — labels are the lowercase member *values* (see chronos_core.models.enums).
time_precision = postgresql.ENUM(
    "exact", "day", "month", "year", "decade", "century", "era",
    name="time_precision", create_type=False,
)
event_status = postgresql.ENUM(
    "draft", "published", "merged", "retracted",
    name="event_status", create_type=False,
)
ingest_state = postgresql.ENUM(
    "new", "normalized", "published", "discarded",
    name="ingest_state", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for enum in (time_precision, event_status, ingest_state):
        enum.create(bind, checkfirst=True)

    uuid_pk = sa.text("gen_random_uuid()")
    now = sa.text("now()")

    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=uuid_pk),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("publisher", sa.String(255)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("snapshot_key", sa.Text()),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("quality_score", sa.SmallInteger(), nullable=False, server_default=sa.text("50")),
        sa.Column("kind", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.UniqueConstraint("content_hash", name="uq_sources_content_hash"),
    )

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=uuid_pk),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("body", sa.Text()),
        sa.Column("t_start", sa.Float(), nullable=False),
        sa.Column("t_end", sa.Float(), nullable=False),
        sa.Column("time_precision", time_precision, nullable=False, server_default=sa.text("'day'")),
        sa.Column("instant", sa.DateTime(timezone=True)),
        sa.Column("category", sa.String(64)),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("severity", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("severity_breakdown", postgresql.JSONB()),
        sa.Column("confidence", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("geom", Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False)),
        sa.Column("geo_label", sa.Text()),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("status", event_status, nullable=False, server_default=sa.text("'published'")),
        sa.Column("merged_into", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_agent", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.ForeignKeyConstraint(["merged_into"], ["events.id"], name="fk_events_merged_into_events", ondelete="SET NULL"),
    )
    op.create_index("ix_events_t_start", "events", ["t_start"])
    op.create_index("ix_events_t_end", "events", ["t_end"])
    op.create_index("ix_events_category", "events", ["category"])
    op.create_index("ix_events_severity", "events", ["severity"])
    op.create_index("ix_events_tags", "events", ["tags"], postgresql_using="gin")
    op.create_index("ix_events_geom", "events", ["geom"], postgresql_using="gist")

    op.create_table(
        "event_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=uuid_pk),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("t_start", sa.Float(), nullable=False),
        sa.Column("t_end", sa.Float(), nullable=False),
        sa.Column("subject_precision", time_precision, nullable=False, server_default=sa.text("'era'")),
        sa.Column("subject_geom", Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False)),
        sa.Column("subject_event_id", postgresql.UUID(as_uuid=True)),
        sa.Column("detail", sa.Text()),
        sa.Column("confidence", sa.SmallInteger(), nullable=False, server_default=sa.text("50")),
        sa.Column("extracted_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name="fk_event_references_event_id_events", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_event_id"], ["events.id"], name="fk_event_references_subject_event_id_events", ondelete="SET NULL"),
    )
    op.create_index("ix_event_references_event_id", "event_references", ["event_id"])
    op.create_index("ix_event_references_t_start", "event_references", ["t_start"])
    op.create_index("ix_event_references_geom", "event_references", ["subject_geom"], postgresql_using="gist")

    op.create_table(
        "event_sources",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("relation", sa.String(32), nullable=False, server_default=sa.text("'reports'")),
        sa.Column("added_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name="fk_event_sources_event_id_events", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_event_sources_source_id_sources", ondelete="CASCADE"),
    )

    op.create_table(
        "ingest_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=uuid_pk),
        sa.Column("feed", sa.String(128), nullable=False),
        sa.Column("external_id", sa.String(512)),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("state", ingest_state, nullable=False, server_default=sa.text("'new'")),
        sa.UniqueConstraint("feed", "external_id", name="uq_ingest_items_feed_external_id"),
    )

    op.create_table(
        "config",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )

    op.create_table(
        "config_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=uuid_pk),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("old_value", postgresql.JSONB()),
        sa.Column("new_value", postgresql.JSONB()),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True)),
        sa.Column("note", sa.Text()),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )


def downgrade() -> None:
    op.drop_table("config_audit")
    op.drop_table("config")
    op.drop_table("ingest_items")
    op.drop_table("event_sources")
    op.drop_index("ix_event_references_geom", table_name="event_references")
    op.drop_index("ix_event_references_t_start", table_name="event_references")
    op.drop_index("ix_event_references_event_id", table_name="event_references")
    op.drop_table("event_references")
    for name in ("ix_events_geom", "ix_events_tags", "ix_events_severity",
                 "ix_events_category", "ix_events_t_end", "ix_events_t_start"):
        op.drop_index(name, table_name="events")
    op.drop_table("events")
    op.drop_table("sources")
    bind = op.get_bind()
    for enum in (ingest_state, event_status, time_precision):
        enum.drop(bind, checkfirst=True)
