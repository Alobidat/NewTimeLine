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
from chronos_core.schemas.social import UserSummary

__all__ = [
    "EntityRead",
    "EntityRole",
    "RelatedEvent",
    "ChainEdge",
    "ChainResponse",
    "SearchResults",
]


class SearchResults(BaseModel):
    """Faceted search response (event-presentation.md §5.1, ADR-0022).

    A single query fans out across events, *actors* (person/org entities) and *places*
    (place entities) so the user can pivot. ``collecting`` flags that a live on-demand
    collection job was enqueued for ``subject`` — the client then follows ``/search/stream``
    to refresh as freshly-collected events land ("showing N results, collecting more…")."""

    subject: str                       # the combined query string the collector searches with
    collecting: bool = False           # a "collect" job was enqueued for this subject
    events: list[EventRead] = Field(default_factory=list)
    actors: list[EntityRead] = Field(default_factory=list)   # person | org
    places: list[EntityRead] = Field(default_factory=list)   # place
    creators: list[UserSummary] = Field(default_factory=list)  # users/bots (author search)


class RelatedEvent(BaseModel):
    """An event reached from another via one graph edge.

    ``origin`` distinguishes who asserted the edge: ``user`` (a person added it via the
    interaction API, ``event_relations.created_by`` is a user UUID) vs ``agent`` (the
    relation-linker / enricher produced it). ``added_by`` carries the raw provenance label
    (the user id or the agent run name) for clients that want to attribute it precisely."""

    event: EventRead
    kind: str                # causal | precursor | same-place | same-actor | thematic | sequel
    weight: float
    direction: str           # back (led to) | forward (caused)
    origin: str = "agent"    # user | agent
    added_by: str | None = None
    # The related event's hero media, so the client can render it full-screen when the user walks
    # to it (left/right) — without these it had no media and showed a black page. Only events with
    # a displayable hero are returned, so a lateral walk never lands on an empty card.
    hero_media_id: uuid.UUID | None = None
    hero_is_clip: bool = False


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
