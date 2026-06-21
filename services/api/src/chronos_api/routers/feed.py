"""Video-first feed/recommendation API (ADR-0027/0028, social-and-feed §4-5).

    GET /feed/{tab}?cursor=&limit=    tab ∈ foryou | following | discover

Returns ``{tab, items:[{event, hero_media_id, score}], next_cursor}`` (the client contract).
All three tabs prefer events that HAVE a hero clip (media-richness, ADR-0024).

Reads use ``get_actor`` (anonymous browse allowed); For-You folds in the caller's interest
profile when they are signed in. A ``view`` activity row is recorded for the served events so
the interest profile + seen-suppression learn from the feed itself.
"""

from __future__ import annotations

import uuid

from chronos_core import interest, social_repo
from chronos_core.schemas.social import FeedResponse
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api import feed_queries
from chronos_api.auth_stub import get_actor
from chronos_api.deps import get_session

router = APIRouter(prefix="/feed", tags=["feed"])

_TABS = ("foryou", "following", "discover")


@router.get("/{tab}", response_model=FeedResponse)
async def feed(
    tab: str,
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> FeedResponse:
    """A page of the requested feed tab (video-first)."""
    if tab not in _TABS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown feed tab: {tab}")

    if tab == "foryou":
        profile = await interest.compute_profile(session, actor)
        resp = await feed_queries.fetch_foryou(
            session, user_id=actor, cursor=cursor, limit=limit, profile=profile
        )
    elif tab == "following":
        resp = await feed_queries.fetch_following(
            session, user_id=actor, cursor=cursor, limit=limit
        )
    else:  # discover
        resp = await feed_queries.fetch_discover(
            session, user_id=actor, cursor=cursor, limit=limit
        )

    # Record a lightweight view of the served events so the profile + seen-suppression learn.
    for item in resp.items:
        await social_repo.record_activity(
            session, user_id=actor, kind="view", target_type="event", target_id=item.event.id
        )
    return resp
