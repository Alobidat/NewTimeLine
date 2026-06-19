"""API DTOs for media attached to events (images / video clips / external embeds).

The client decides how to render from ``kind`` + the available URLs: a stored binary
(``storage_key`` → served/signed by the API later), an external player (``embed_url``),
and an optional ``thumbnail_key`` for the poster frame.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class MediaRead(BaseModel):
    """A media item as shown on an event detail view."""

    id: uuid.UUID
    kind: str                       # image | video | audio | embed
    role: str = "gallery"           # hero | gallery | inline | related
    rank: int = 0
    storage_key: str | None = None
    embed_url: str | None = None
    thumbnail_key: str | None = None
    mime: str | None = None
    width: int | None = None
    height: int | None = None
    duration_s: int | None = None
    caption: str | None = None
    credit: str | None = None
    license: str | None = None
    status: str = "pending"
