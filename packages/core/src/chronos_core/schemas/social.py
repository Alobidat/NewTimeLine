"""API DTOs for the social graph, promotes, interest profile, and feed (Phase 4-B).

Request bodies validate the small closed value-sets (``target_type`` / ``value``) at the edge;
responses are flat, client-friendly shapes. The actor is never taken from the request body —
it comes from the auth seam (``get_actor`` / ``require_verified_actor``).
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from chronos_core.schemas.event import EventRead

__all__ = [
    "FollowResult",
    "FollowCounts",
    "FollowTarget",
    "FollowList",
    "PromoteCast",
    "PromoteResult",
    "PromoteSummary",
    "InterestProfile",
    "FeedItem",
    "FeedResponse",
]

FollowTargetType = Literal["user", "entity", "event"]
PromoteTargetType = Literal["event", "relation", "source", "entity"]
FeedTab = Literal["foryou", "following", "discover"]


# --- follows --------------------------------------------------------------------------


class FollowResult(BaseModel):
    """Outcome of a follow/unfollow operation."""

    target_type: FollowTargetType
    target_id: uuid.UUID
    following: bool                    # True if the caller now follows the target


class FollowCounts(BaseModel):
    """Follower/following counts for a target (or a user)."""

    target_type: str
    target_id: uuid.UUID
    followers: int = 0                 # who follows this target
    following: int = 0                 # what this user follows (only meaningful for users)


class FollowTarget(BaseModel):
    """A single (target_type, target_id) edge endpoint."""

    target_type: str
    target_id: uuid.UUID


class FollowList(BaseModel):
    """A page of follower or following edges."""

    items: list[FollowTarget] = Field(default_factory=list)
    count: int = 0


# --- promotes -------------------------------------------------------------------------


class PromoteCast(BaseModel):
    """Promote (+1) or demote (-1) a graph object. ``value=0`` clears the caller's vote."""

    target_type: PromoteTargetType
    target_id: uuid.UUID
    value: Literal[-1, 0, 1]


class PromoteResult(BaseModel):
    """Outcome of a cast: the caller's stored value + the refreshed aggregate."""

    target_type: PromoteTargetType
    target_id: uuid.UUID
    mine: int                          # the caller's current value (-1/0/+1)
    score: int                         # sum of all promote values
    up: int = 0
    down: int = 0


class PromoteSummary(BaseModel):
    """Aggregate promote tallies for a target + the caller's own value."""

    target_type: str
    target_id: uuid.UUID
    score: int = 0
    up: int = 0
    down: int = 0
    mine: int = 0


# --- interest profile -----------------------------------------------------------------


class InterestProfile(BaseModel):
    """A decayed, weighted interest profile (debug/inspection of GET /me/interests).

    Each map is ``{id-or-name: weight}`` (descending). ``entities``/``sources`` key by uuid
    (string); ``categories`` by category name; ``places`` by entity uuid (kind=place)."""

    entities: dict[str, float] = Field(default_factory=dict)
    categories: dict[str, float] = Field(default_factory=dict)
    places: dict[str, float] = Field(default_factory=dict)
    sources: dict[str, float] = Field(default_factory=dict)
    sample_size: int = 0               # activity rows considered


# --- feed -----------------------------------------------------------------------------


class FeedItem(BaseModel):
    """One ranked feed entry: the event, its hero media, and the blended score."""

    event: EventRead
    hero_media_id: uuid.UUID | None = None
    score: float = 0.0


class FeedResponse(BaseModel):
    """A page of the feed. ``next_cursor`` is opaque; pass it back to page forward."""

    tab: FeedTab
    items: list[FeedItem] = Field(default_factory=list)
    next_cursor: str | None = None
