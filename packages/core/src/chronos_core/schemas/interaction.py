"""API DTOs for the interaction substrate (ADR-0025): comments, reactions, source votes,
and user-created event links.

Request bodies validate the small closed value-sets (``kind`` / ``verdict``) so a bad write
is rejected at the edge; responses are flat, client-friendly shapes. The actor is never taken
from the request body — it comes from the ``get_actor`` identity stub.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "CommentAuthor",
    "CommentCreate",
    "CommentUpdate",
    "CommentRead",
    "EventStats",
    "ReactionToggle",
    "ReactionToggleResult",
    "ReactionSummary",
    "SourceVoteCast",
    "SourceVoteResult",
    "SourceVoteSummary",
    "EventLinkCreate",
    "EventLinkResult",
]

ReactionKind = Literal["like", "dislike", "important", "doubt"]
VoteVerdict = Literal["corroborate", "dispute", "irrelevant"]
CommentStatus = Literal["visible", "flagged", "removed"]


class EventStats(BaseModel):
    """Aggregate engagement counts for an event — the numbers shown on the feed action rail."""

    event_id: uuid.UUID
    reactions: int = 0  # total reactions across all kinds
    reaction_counts: dict[str, int] = Field(default_factory=dict)  # per-kind breakdown
    comments: int = 0  # visible comments
    promote_score: int = 0  # net promote (up - down)
    promotes_up: int = 0
    promotes_down: int = 0
    followers: int = 0  # users following this event
    bookmarks: int = 0  # users who saved it


# --- comments -------------------------------------------------------------------------


class CommentCreate(BaseModel):
    """Post a comment (or a reply when ``parent_id`` is given)."""

    body: str = Field(min_length=1, max_length=10_000)
    parent_id: uuid.UUID | None = None


class CommentUpdate(BaseModel):
    """Edit a comment's body (author only)."""

    body: str = Field(min_length=1, max_length=10_000)


class CommentAuthor(BaseModel):
    """The public identity of a comment's author (for the avatar + profile link)."""

    id: uuid.UUID
    handle: str
    display_name: str | None = None
    avatar_url: str | None = None


class CommentRead(BaseModel):
    """A comment as returned to clients, enriched with its author + reaction state so a thread
    renders in one round-trip."""

    id: uuid.UUID
    event_id: uuid.UUID
    user_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    body: str
    score: int
    status: CommentStatus
    created_at: datetime
    updated_at: datetime
    author: CommentAuthor | None = None
    # Aggregate reaction counts per kind on this comment + the caller's own kinds.
    reactions: dict[str, int] = Field(default_factory=dict)
    my_reactions: list[str] = Field(default_factory=list)


# --- reactions ------------------------------------------------------------------------


class ReactionToggle(BaseModel):
    """Toggle one reaction kind on an event for the calling actor."""

    kind: ReactionKind


class ReactionToggleResult(BaseModel):
    """Outcome of a toggle: whether the reaction is now active + the fresh aggregate."""

    kind: ReactionKind
    active: bool                       # True if just added, False if just removed
    counts: dict[str, int]             # kind -> count, after the toggle
    mine: list[ReactionKind]           # the actor's kinds on this event, after the toggle


class ReactionSummary(BaseModel):
    """Aggregate reaction counts for an event + the caller's own set."""

    event_id: uuid.UUID
    counts: dict[str, int] = Field(default_factory=dict)   # kind -> count
    mine: list[ReactionKind] = Field(default_factory=list)


# --- source votes ---------------------------------------------------------------------


class SourceVoteCast(BaseModel):
    """Cast (or change) a verdict on a source's relevance to an event."""

    source_id: uuid.UUID
    verdict: VoteVerdict


class SourceVoteResult(BaseModel):
    """Outcome of a cast: the stored verdict + the refreshed per-source aggregate."""

    source_id: uuid.UUID
    verdict: VoteVerdict
    tallies: dict[str, dict[str, int]]   # source_id(str) -> {verdict -> count}


class SourceVoteSummary(BaseModel):
    """Per-source verdict tallies for an event, plus the caller's own verdicts."""

    event_id: uuid.UUID
    tallies: dict[str, dict[str, int]] = Field(default_factory=dict)  # source_id -> verdict -> count
    mine: dict[str, VoteVerdict] = Field(default_factory=dict)        # source_id -> the actor's verdict


# --- user event links -----------------------------------------------------------------


class EventLinkCreate(BaseModel):
    """Assert a relation between two events (a user-added history-graph edge).

    ``kind`` defaults to ``thematic`` (the safe, non-causal default for user links)."""

    src_event: uuid.UUID
    dst_event: uuid.UUID
    kind: str = "thematic"


class EventLinkResult(BaseModel):
    """Outcome of a create/remove link operation."""

    src_event: uuid.UUID
    dst_event: uuid.UUID
    kind: str
    created: bool = False              # True if a new edge was inserted
    removed: bool = False              # True if an existing edge was deleted
