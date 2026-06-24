"""Friendship — an explicit, mutual relationship via request + accept.

One row per unordered pair (a DB-side functional unique index on
``(LEAST(req,addr), GREATEST(req,addr))`` enforces it). ``requester_id`` made the request;
``status`` is ``pending`` until the ``addressee`` accepts. Friends get a higher access tier
than followers in the privacy resolver. ``user_id``s are plain uuids with no FK (the GDPR
purge fans out explicitly).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import UuidPk

FRIENDSHIP_STATUSES = ("pending", "accepted")


class Friendship(UuidPk, Base):
    """A friend request / accepted friendship between two users."""

    __tablename__ = "friendships"

    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    addressee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_friendships_addressee", "addressee_id", "status"),
        Index("ix_friendships_requester", "requester_id", "status"),
    )
