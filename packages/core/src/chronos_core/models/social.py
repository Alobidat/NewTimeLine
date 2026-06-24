"""Social-graph + engagement ORM models (Phase 4-B, ADR-0025/0027/0028).

Three tables (migration 0007):

- :class:`Follow`      — a user follows a user | entity | event (data-model §3.5).
- :class:`ActivityLog` — every meaningful action with a weight; the interest-profile substrate.
- :class:`Promote`     — a generic up/down promote vote on event | relation | source | entity.

``user_id`` / ``target_id`` are plain ``uuid`` columns with **no FK** — same Phase-4-decoupling
choice as the 0005 interaction tables (the GDPR purge fans out explicitly in
chronos_core.accounts_repo). Closed value sets for ``target_type`` / ``kind`` / ``value`` are
enforced in the schema/repository layer, not as DB enums.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    Index,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import Timestamps

# Closed value sets (validated in the schema/repository layer; mirrored here for callers).
FOLLOW_TARGETS = ("user", "entity", "event")
PROMOTE_TARGETS = ("event", "relation", "source", "entity")
ACTIVITY_KINDS = (
    "view", "watch", "like", "comment", "promote", "follow", "upload", "dwell", "share",
)
ACTIVITY_TARGETS = ("event", "entity", "source", "relation")


class Follow(Base):
    """A directed follow edge. PK on (user, target_type, target_id) → at most one per target."""

    __tablename__ = "follows"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), primary_key=True)  # user|entity|event
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_follows_target", "target_type", "target_id"),
        Index("ix_follows_user", "user_id"),
    )


class ActivityLog(Base):
    """One recorded engagement action — the substrate for the decayed interest profile."""

    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_activity_user_created", "user_id", "created_at"),
        Index("ix_activity_target", "target_type", "target_id"),
    )


class Promote(Timestamps, Base):
    """A user's up/down promote vote on a graph object (event|relation|source|entity).

    PK on (user, target_type, target_id) → one vote per target per user; ``value`` is +1
    (promote) or -1 (demote). Aggregated promotes feed feed-ranking + later quality signals.
    """

    __tablename__ = "promotes"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    value: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # +1 / -1

    __table_args__ = (Index("ix_promotes_target", "target_type", "target_id"),)


class Bookmark(Base):
    """A user's private save of an event (the "Saved" collection). PK on (user, event) → at
    most one per event. Unlike :class:`Follow`/:class:`Promote` it carries no activity weight —
    a bookmark is a private bookmark, not a public engagement signal — so it is never recorded
    in :class:`ActivityLog`. ``user_id`` is a plain uuid with no FK (Phase-4 decoupling; the
    GDPR purge fans out explicitly in chronos_core.accounts_repo)."""

    __tablename__ = "bookmarks"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_bookmarks_user_created", "user_id", "created_at"),)


class Repost(Base):
    """A user's public re-share of an event to their followers (the feed's "Repost"). PK on
    (user, event) → at most one repost per event. Unlike :class:`Bookmark` this is a *public*
    signal — the reposter's followers see it in their "Following" feed and it shows on the
    reposter's profile — so the repo caller also records an :class:`ActivityLog` ``share`` row.
    ``user_id``/``event_id`` are plain uuids with no FK (the GDPR purge fans out explicitly in
    chronos_core.accounts_repo)."""

    __tablename__ = "reposts"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_reposts_user_created", "user_id", "created_at"),
        Index("ix_reposts_event", "event_id"),
    )
