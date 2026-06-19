"""API DTOs for the entity-anchored history graph: entities, related events, and the
back-and-forth causal *chain* an event sits in.

Direction convention follows ``event_relations`` (src = earlier/cause, dst = later/effect):
- ``back``    → what *led to* this event (ancestors),
- ``forward`` → what this event *caused* (descendants),
- ``both``    → the surrounding chain.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from chronos_core.schemas.entity import EntityRead, EntityRole  # re-exported for callers
from chronos_core.schemas.event import EventRead

__all__ = [
    "EntityRead",
    "EntityRole",
    "RelatedEvent",
    "ChainEdge",
    "ChainResponse",
]


class RelatedEvent(BaseModel):
    """An event reached from another via one graph edge."""

    event: EventRead
    kind: str                # causal | precursor | same-place | same-actor | thematic | sequel
    weight: float
    direction: str           # back (led to) | forward (caused)


class ChainEdge(BaseModel):
    """A directed edge in a chain response (src led to dst)."""

    src: uuid.UUID
    dst: uuid.UUID
    kind: str
    weight: float


class ChainResponse(BaseModel):
    """The causal chain around a root event: the reachable nodes + the edges between them."""

    root: uuid.UUID
    direction: str
    depth: int
    nodes: list[EventRead] = Field(default_factory=list)
    edges: list[ChainEdge] = Field(default_factory=list)
