"""API DTOs for entities (people / orgs / places / topics) and their role on an event.

No dependency on the event schema (only :mod:`chronos_core.schemas.geo`), so the event
detail view can embed entities without an import cycle.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from chronos_core.schemas.geo import GeoPoint


class EntityRead(BaseModel):
    """A person/org/place/topic. ``event_count`` is filled by listing endpoints."""

    id: uuid.UUID
    kind: str
    name: str
    external_id: str | None = None
    geo: GeoPoint | None = None
    event_count: int | None = None


class EntityRole(BaseModel):
    """An entity and the role it plays in a given event (actor | location | subject …)."""

    entity: EntityRead
    role: str
