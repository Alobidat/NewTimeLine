"""Privacy resolver — the viewer↔target relationship and whether it satisfies an audience.

Used by the **profile** gate (bio/posts/followers/following/interactions) and the per-user
``uploads``/``interactions`` endpoints. The **feed** gate is inlined as SQL in
``feed_queries._VISIBILITY`` (same semantics) for performance.

Relationship tiers, most-trusted first: ``self`` > ``friend`` > ``follower`` > ``none``. A
friend therefore also satisfies a ``followers`` audience.
"""

from __future__ import annotations

import uuid

from chronos_core import friends_repo, social_repo
from sqlalchemy.ext.asyncio import AsyncSession

# Relationship of a viewer to a target.
SELF, FRIEND, FOLLOWER, NONE = "self", "friend", "follower", "none"


async def relationship(
    session: AsyncSession, viewer: uuid.UUID, target: uuid.UUID
) -> str:
    """The viewer's relationship to ``target``: self|friend|follower|none."""
    if viewer == target:
        return SELF
    if await friends_repo.are_friends(session, viewer, target):
        return FRIEND
    if await social_repo.is_following(
        session, user_id=viewer, target_type="user", target_id=target
    ):
        return FOLLOWER
    return NONE


def satisfies(rel: str, audience: str) -> bool:
    """Whether a viewer with relationship ``rel`` may see content with the given ``audience``
    (public|followers|friends|only_me)."""
    if rel == SELF:
        return True
    if audience == "public":
        return True
    if audience == "followers":
        return rel in (FRIEND, FOLLOWER)
    if audience == "friends":
        return rel == FRIEND
    # only_me (or anything unknown) → only self, handled above.
    return False
