"""API DTOs for the social graph, promotes, interest profile, and feed (Phase 4-B).

Request bodies validate the small closed value-sets (``target_type`` / ``value``) at the edge;
responses are flat, client-friendly shapes. The actor is never taken from the request body —
it comes from the auth seam (``get_actor`` / ``require_verified_actor``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from chronos_core.schemas.event import EventRead
from chronos_core.schemas.interaction import CommentAuthor

__all__ = [
    "FollowResult",
    "FollowCounts",
    "FollowTarget",
    "FollowList",
    "FollowedItem",
    "NotificationRead",
    "NotificationList",
    "UserSummary",
    "UserSummaryList",
    "UserProfile",
    "BookmarkResult",
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


class UserSummary(BaseModel):
    """A user in a follower/following list: identity + whether the caller follows them."""

    id: uuid.UUID
    handle: str
    display_name: str | None = None
    avatar_url: str | None = None
    following: bool = False  # does the *caller* follow this user (for a follow-back button)


class UserSummaryList(BaseModel):
    """A page of users (followers or following)."""

    items: list[UserSummary] = Field(default_factory=list)
    count: int = 0


class InteractionItem(BaseModel):
    """One recent action a user took on a (visible) event — for the profile Interactions tab."""

    kind: str  # react|comment|promote|follow|...
    event: EventRead
    created_at: datetime


class UserProfile(BaseModel):
    """A public user profile: identity, reputation, follow/friend counts, the caller's relation,
    and which audience-gated facets the caller may view."""

    id: uuid.UUID
    handle: str
    display_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None  # nulled when the caller can't view it
    reputation: int = 0
    followers: int = 0
    following: int = 0
    friends: int = 0
    is_following: bool = False  # does the caller follow this user
    is_self: bool = False
    friend_state: str = "none"  # self|friends|incoming|outgoing|none
    friendship_id: uuid.UUID | None = None
    # Per-facet view permissions for the caller (drives which tabs/lists the client shows).
    can_view_posts: bool = True
    can_view_followers: bool = True
    can_view_following: bool = True
    can_view_interactions: bool = True


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


class NotificationRead(BaseModel):
    """One in-app notification, resolved for display: who did what to which event, and when."""

    id: uuid.UUID
    kind: str  # follow | like | comment | reply | repost
    actor: CommentAuthor | None = None
    event_id: uuid.UUID | None = None
    event_title: str | None = None
    read: bool = False
    created_at: datetime


class NotificationList(BaseModel):
    """A page of notifications + the unread count for the bell badge."""

    items: list[NotificationRead] = Field(default_factory=list)
    unread: int = 0


class FollowedItem(BaseModel):
    """One thing a user follows — a ``user``, an ``entity`` (e.g. NASA), or an ``event`` —
    resolved to display fields for the profile's Following list. ``handle``/``avatar_url`` are
    user-only; ``following`` is whether the *caller* also follows it (drives the toggle)."""

    kind: str  # 'user' | 'entity' | 'event'
    id: uuid.UUID
    name: str
    handle: str | None = None
    avatar_url: str | None = None
    following: bool = True


# --- bookmarks ------------------------------------------------------------------------


class BookmarkResult(BaseModel):
    """Outcome of a bookmark/unbookmark on an event (+ the caller's post-state)."""

    event_id: uuid.UUID
    bookmarked: bool                   # True if the caller now has the event saved


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
    (string); ``categories`` by category name; ``places`` by entity uuid (kind=place).
    ``labels`` resolves those uuids → human display names for the UI (entity/source names);
    keys absent from it (e.g. categories) are already human-readable."""

    entities: dict[str, float] = Field(default_factory=dict)
    categories: dict[str, float] = Field(default_factory=dict)
    places: dict[str, float] = Field(default_factory=dict)
    sources: dict[str, float] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)   # uuid -> display name
    sample_size: int = 0               # activity rows considered


# --- feed -----------------------------------------------------------------------------


class FeedItem(BaseModel):
    """One ranked feed entry: the event, its hero media, and the blended score."""

    event: EventRead
    hero_media_id: uuid.UUID | None = None
    # Whether the hero media is a playable clip (video/embed) vs a still image. The video-first
    # client plays clips in a <video> but must render image heroes as a full-bleed photo — a
    # <video> can't decode a JPEG, so without this flag image heroes showed as a black screen.
    hero_is_clip: bool = False
    score: float = 0.0
    # Who to attribute the clip to on the rail (avatar + follow): the uploading *user* for
    # user-generated clips, else the clip's primary *entity* (e.g. NASA) for agent-curated
    # world events — so every clip has a followable face. ``author_kind`` says which, so the
    # client follows the right target (``user`` vs ``entity``). None only when nothing is known.
    author: CommentAuthor | None = None
    author_kind: str = "user"  # 'user' | 'entity'


class FeedResponse(BaseModel):
    """A page of the feed. ``next_cursor`` is opaque; pass it back to page forward."""

    tab: FeedTab
    items: list[FeedItem] = Field(default_factory=list)
    next_cursor: str | None = None
