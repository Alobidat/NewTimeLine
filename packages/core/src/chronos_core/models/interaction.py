"""Interaction ORM models — the user-engagement substrate (ADR-0025).

Three tables back the Phase 3d interaction foundations (docs/data-model.md §3.5–3.7):

- :class:`Comment`   — threaded comments on an event (``parent_id`` self-FK).
- :class:`Reaction`  — one-of-each-kind reaction per (user, event) (PK on the triple).
- :class:`SourceVote` — a community verdict on a source's relevance to an event.

``user_id`` is a plain ``uuid`` with **no hard FK to users** for now: the accounts system
(``users`` / ``user_identities``) lands with Phase-4 auth, and writes are gated by the
``get_actor`` identity stub today. The column is Phase-4-compatible — a FK can be added in a
later migration once ``users`` exists. The valid value sets for ``kind`` / ``verdict`` /
``status`` are enforced in the schema/repository layer (kept as ``text`` like the rest of the
graph, e.g. ``event_relations.kind``), not as DB enums.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import Timestamps, UuidPk

# Valid value sets (validated in the schema/repository layer; mirrored here for callers).
REACTION_KINDS = ("like", "dislike", "important", "doubt")
VOTE_VERDICTS = ("corroborate", "dispute", "irrelevant")
COMMENT_STATUSES = ("visible", "flagged", "removed")


class Comment(UuidPk, Timestamps, Base):
    """A threaded comment on an event. ``parent_id`` links a reply to its parent."""

    __tablename__ = "comments"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    # No FK to users yet (accounts arrive in Phase 4); resolved by the get_actor stub today.
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="visible", nullable=False)

    __table_args__ = (
        Index("ix_comments_event_created", "event_id", "created_at"),
        Index("ix_comments_parent", "parent_id"),
    )


class Reaction(Base):
    """A user's reaction to an event. PK on (user, event, kind) → one of each kind per user."""

    __tablename__ = "reactions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # like|dislike|important|doubt
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_reactions_event", "event_id"),)


class SourceVote(Timestamps, Base):
    """A community verdict on a source's relevance to an event (credibility signal).

    PK on (user, event, source) → one verdict per user per source-on-event. Aggregated,
    reputation-weighted verdicts adjust event ``confidence`` / source ``quality_score`` later.
    """

    __tablename__ = "source_votes"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)  # corroborate|dispute|irrelevant
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    __table_args__ = (Index("ix_source_votes_event", "event_id"),)
