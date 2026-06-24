"""DTOs for the admin moderation queue."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ModerationFlagRead(BaseModel):
    """One open flag + a short preview of the flagged content for the admin queue."""

    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    source: str
    reason: str | None = None
    severity: int
    status: str
    created_at: datetime
    preview: str | None = None  # title (event) or body snippet (comment)
    held: bool = False  # whether the target is currently held out of view


class ModerationQueue(BaseModel):
    items: list[ModerationFlagRead] = Field(default_factory=list)
    count: int = 0
