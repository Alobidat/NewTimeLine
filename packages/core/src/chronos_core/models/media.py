"""Media + EventMedia ORM models — rich content (images / video clips) for event detail.

Binaries live in the object store (``storage_key``); external players (e.g. YouTube) are
referenced via ``embed_url`` with status ``external``. ``event_media`` is a link table so
one media item can attach to several related events, and links may be added later by a new
source OR by a user (``added_by`` records which). Gathering + storage design: ADR-0017.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import Timestamps, UuidPk


class Media(UuidPk, Timestamps, Base):
    """An image, video, audio clip, or external embed referenced by one or more events.

    Archival fields (ADR-0018 / chronos_core.domain.media_policy) decide whether the binary
    is stored locally (``disposition`` pin/archive) or merely linked (``link``), and track
    observed availability so a durable archive can later be released.
    """

    __tablename__ = "media"

    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # image|video|audio|embed
    storage_key: Mapped[str | None] = mapped_column(Text)   # object-store key of the binary
    source_url: Mapped[str | None] = mapped_column(Text)    # origin URL it was found/fetched at
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
    # pending=queued for fetch, stored=in object store, external=link/embed-only,
    # released=was stored, dropped after proving durable, failed, gone=source vanished
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    added_by: Mapped[str | None] = mapped_column(String(64))

    # --- archival policy (ADR-0018) ---
    # disposition: pin | archive | link
    disposition: Mapped[str] = mapped_column(String(16), default="archive", nullable=False)
    sensitivity: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)  # 0..100
    persistence_confidence: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    origin_kind: Mapped[str | None] = mapped_column(String(32))  # news|social|encyclopedia|...
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # manual pin
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # avail_state: unknown | available | moved | gone
    avail_state: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)

    # Creator-Studio edit spec applied by the transcode agent when building the web variant —
    # e.g. {"trim_start": 1.5, "trim_end": 9.0, "speed": 2.0}. Null = no edits (Phase 1).
    edit_spec: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (UniqueConstraint("content_hash", name="uq_media_content_hash"),)


class MediaVariant(UuidPk, Timestamps, Base):
    """A derived rendition of a video ``Media`` — e.g. a web-playable mp4 (H.264/AAC) produced
    by the transcode agent so every clip plays cross-browser regardless of its source codec.

    ``rendition`` names the variant (``web`` = the default web-safe mp4). A variant may be a
    real re-encode stored under its own ``storage_key``, or a **passthrough** that points at the
    original's key when the source was already web-safe (so a clip is processed exactly once).
    """

    __tablename__ = "media_variants"

    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    rendition: Mapped[str] = mapped_column(String(32), nullable=False)  # web | (future: hls, …)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str | None] = mapped_column(String(128))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="stored", nullable=False)

    __table_args__ = (
        UniqueConstraint("media_id", "rendition", name="uq_media_variant_rendition"),
        Index("ix_media_variants_media", "media_id"),
    )


class MediaSource(Base):
    """Each distinct host URL a media item has been seen at — the corroboration signal for
    'available at one or more sources'. ``is_stable`` marks durable hosts (Wikimedia, etc.)."""

    __tablename__ = "media_sources"

    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    source_url: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    is_stable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avail_state: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    last_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_media_sources_media", "media_id"),)


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
