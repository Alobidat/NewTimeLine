"""Media + EventMedia ORM models — rich content (images / video clips) for event detail.

Binaries live in the object store (``storage_key``); external players (e.g. YouTube) are
referenced via ``embed_url`` with status ``external``. ``event_media`` is a link table so
one media item can attach to several related events, and links may be added later by a new
source OR by a user (``added_by`` records which). Gathering + storage design: ADR-0017.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import Timestamps, UuidPk


class Media(UuidPk, Timestamps, Base):
    """An image, video, audio clip, or external embed referenced by one or more events."""

    __tablename__ = "media"

    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # image|video|audio|embed
    storage_key: Mapped[str | None] = mapped_column(Text)   # object-store key of the binary
    source_url: Mapped[str | None] = mapped_column(Text)    # where it was found/fetched
    embed_url: Mapped[str | None] = mapped_column(Text)      # external player URL (not stored)
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    mime: Mapped[str | None] = mapped_column(String(128))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    caption: Mapped[str | None] = mapped_column(Text)
    credit: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(64))
    # pending=queued for fetch, stored=in object store, external=embed-only, failed
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    added_by: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("content_hash", name="uq_media_content_hash"),)


class EventMedia(Base):
    """Link table: a media item shown on an event (hero | gallery | inline | related)."""

    __tablename__ = "event_media"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), default="gallery", nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_by: Mapped[str | None] = mapped_column(String(64))  # agent run OR user id
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_event_media_media", "media_id"),)
