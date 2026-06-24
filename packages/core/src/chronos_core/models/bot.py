"""AI-user (bot persona) ORM model — the side table behind ``users.is_bot`` (ADR: AI users).

A bot is an ordinary :class:`~chronos_core.models.user.User` row (``is_bot=True``) provisioned
server-side with a ``provider="system"`` identity. Its persona, interests, posting cadence,
rate caps, quality threshold, enable flags, and running stats live here in a 1:1 side table so
the hot ``users`` table (read on every comment/feed author render) stays lean — "is this a bot?"
is the cheap indexed ``users.is_bot`` predicate, no join required.

The autonomous engines (``persona-post`` / ``persona-interact`` / ``bots-tick``) read this row to
decide *who* acts, *how often*, and *what* they care about; admins flip ``enabled`` to suspend a
bot and tune the cadence/cap/threshold knobs. ``seed`` is the deterministic persona seed so a
re-run of the generator skips bots that already exist.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import Timestamps


class BotProfile(Timestamps, Base):
    """Persona + behaviour config + stats for one AI user (1:1 with ``users.id``)."""

    __tablename__ = "bot_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Free-text persona/voice notes (the rationale the generator wrote for this character).
    persona: Mapped[str | None] = mapped_column(Text)
    # Interest tags (sports|science|news|politics|finance|tech|history|culture|nature|space|…).
    interests: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    # {"science": 0.8, "space": 0.2, …} — weights drive topic selection when posting.
    interest_weights: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    tone: Mapped[str | None] = mapped_column(String(64))  # e.g. "wry", "earnest", "analytical"

    # Cadence (minutes between actions) + daily caps — the scheduler honours these.
    post_cadence_min: Mapped[int] = mapped_column(Integer, default=720, nullable=False)
    interact_cadence_min: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    # 0..100 quality bar a discovered clip must clear to be posted.
    quality_threshold: Mapped[int] = mapped_column(SmallInteger, default=60, nullable=False)
    daily_post_cap: Mapped[int] = mapped_column(SmallInteger, default=3, nullable=False)
    daily_interact_cap: Mapped[int] = mapped_column(SmallInteger, default=30, nullable=False)

    # Enable flags — admin suspend = enabled=False; finer-grained gating per activity kind.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    posts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    interacts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_interact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interactions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Deterministic persona seed (idempotent generation: skip a seed that already has a bot).
    seed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
