"""Entity + EventEntity ORM models — people, orgs, places, topics tagged on events.

Entities are the anchors of the history graph: tagging "United States" and "Iran" on the
relevant events is what lets the relation-linker connect them across time and what powers
"all events linking the US and Iran" (docs/data-model.md §3.3). Resolution is by
``external_id`` (Wikidata QID) when known, else by ``(kind, name_key)``.
"""

from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.event import EMBEDDING_DIM
from chronos_core.models.mixins import Timestamps, UuidPk


class Entity(UuidPk, Timestamps, Base):
    """A person, organization, place, or topic that events refer to."""

    __tablename__ = "entities"

    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # person|org|place|topic
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_key: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(64))  # Wikidata QID
    geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False)
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    meta: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("kind", "external_id", name="uq_entities_kind_external_id"),
        UniqueConstraint("kind", "name_key", name="uq_entities_kind_name_key"),
        Index("ix_entities_kind", "kind"),
        Index("ix_entities_geom", "geom", postgresql_using="gist"),
        Index(
            "ix_entities_name_trgm", "name",
            postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class EventEntity(Base):
    """Link table: an entity's role in an event (actor | location | subject | affected)."""

    __tablename__ = "event_entities"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    added_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_event_entities_entity", "entity_id"),)
