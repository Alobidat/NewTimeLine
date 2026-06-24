"""Admin DTOs for AI-user (bot) management (the roster the Admin Portal renders)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class BotView(BaseModel):
    """One row in the AI-users roster."""

    id: uuid.UUID
    handle: str
    display_name: str | None
    avatar_url: str | None
    interests: list[str]
    tone: str | None
    enabled: bool
    posts_enabled: bool
    interacts_enabled: bool
    posts_count: int
    interactions_count: int
    last_post_at: datetime | None
    last_interact_at: datetime | None
    created_at: datetime


class BotPostView(BaseModel):
    """A recent post by a bot (for the detail page)."""

    event_id: uuid.UUID
    title: str
    status: str
    category: str | None
    created_at: datetime


class BotCommentView(BaseModel):
    event_id: uuid.UUID
    body: str
    created_at: datetime


class BotDetail(BotView):
    """Full bot view: persona + behaviour config + recent activity."""

    persona: str | None
    interest_weights: dict
    post_cadence_min: int
    interact_cadence_min: int
    quality_threshold: int
    daily_post_cap: int
    daily_interact_cap: int
    seed: int
    followers: int
    following: int
    recent_posts: list[BotPostView]
    recent_comments: list[BotCommentView]


class BotUpdate(BaseModel):
    """Admin-editable bot fields (all optional — only provided fields change)."""

    enabled: bool | None = None
    posts_enabled: bool | None = None
    interacts_enabled: bool | None = None
    post_cadence_min: int | None = None
    interact_cadence_min: int | None = None
    quality_threshold: int | None = None
    daily_post_cap: int | None = None
    daily_interact_cap: int | None = None


class BotRoster(BaseModel):
    """Paginated roster + totals for the list screen header."""

    total: int
    enabled: int
    bots: list[BotView]


class BootstrapRequest(BaseModel):
    count: int = 50
    posts_per_bot: int = 2


class ActionResult(BaseModel):
    ok: bool
    detail: str | None = None
