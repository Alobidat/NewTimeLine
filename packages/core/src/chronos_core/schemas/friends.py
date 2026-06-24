"""DTOs for the friends surface (request + accept, mutual)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from chronos_core.schemas.social import UserSummary

__all__ = [
    "FriendStateResult",
    "FriendRequestRead",
    "FriendRequestList",
    "FriendList",
]

# self|friends|incoming|outgoing|none — drives the profile Friend button.
FriendStateValue = str


class FriendStateResult(BaseModel):
    """The viewer's friendship relation to a target."""

    target_id: uuid.UUID
    state: FriendStateValue
    friendship_id: uuid.UUID | None = None


class FriendRequestRead(BaseModel):
    """A pending request + the other party, for the requests inbox."""

    friendship_id: uuid.UUID
    user: UserSummary
    direction: str  # incoming | outgoing
    created_at: datetime


class FriendRequestList(BaseModel):
    incoming: list[FriendRequestRead] = Field(default_factory=list)
    outgoing: list[FriendRequestRead] = Field(default_factory=list)


class FriendList(BaseModel):
    items: list[UserSummary] = Field(default_factory=list)
    count: int = 0
