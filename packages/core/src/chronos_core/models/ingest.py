"""IngestItem ORM model — raw feed items pre-normalization (audit + replay).

Retaining raw input lets the whole pipeline be replayed after a logic change without
re-fetching feeds (idempotency; see docs/ai-agents.md §4).
"""

from __future__ import annotations

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.enums import IngestState, pg_enum
from chronos_core.models.mixins import UuidPk

_ingest_state_enum = pg_enum(IngestState, "ingest_state")


class IngestItem(UuidPk, Base):
    """One raw item pulled from a feed, deduped by ``(feed, external_id)``."""

    __tablename__ = "ingest_items"

    feed: Mapped[str] = mapped_column(String(128), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(512))
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    state: Mapped[IngestState] = mapped_column(
        _ingest_state_enum, nullable=False, default=IngestState.NEW
    )

    __table_args__ = (
        UniqueConstraint("feed", "external_id", name="uq_ingest_items_feed_external_id"),
    )
