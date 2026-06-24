"""Friendship read/write helpers (request + accept, mutual).

One row per unordered pair. ``request_friend`` is idempotent and **auto-accepts** when a
reverse request is already pending (both sides asked → instant friends). State queries power
the profile Friend button and the privacy resolver. Callers commit.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.models.friendship import Friendship


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _row_for_pair(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID
) -> Friendship | None:
    """The single friendship row for the unordered pair {a, b}, if any."""
    return (
        await session.scalars(
            select(Friendship).where(
                or_(
                    and_(Friendship.requester_id == a, Friendship.addressee_id == b),
                    and_(Friendship.requester_id == b, Friendship.addressee_id == a),
                )
            )
        )
    ).first()


async def request_friend(
    session: AsyncSession, *, requester: uuid.UUID, addressee: uuid.UUID
) -> Friendship:
    """Send (or resolve) a friend request. Raises ``ValueError`` for a self-request.

    - No row yet → create a ``pending`` request.
    - A reverse ``pending`` request exists → **accept** it (mutual) and return it.
    - Already friends / already requested → return the existing row (idempotent)."""
    if requester == addressee:
        raise ValueError("cannot friend yourself")
    existing = await _row_for_pair(session, requester, addressee)
    if existing is not None:
        if existing.status == "pending" and existing.addressee_id == requester:
            # The other side already asked us → accept.
            existing.status = "accepted"
            existing.responded_at = _now()
        return existing
    row = Friendship(requester_id=requester, addressee_id=addressee, status="pending")
    session.add(row)
    await session.flush()
    return row


async def accept_request(
    session: AsyncSession, *, friendship_id: uuid.UUID, user_id: uuid.UUID
) -> Friendship | None:
    """Accept a pending request addressed to ``user_id``. Returns the row, None if not found,
    or raises ``PermissionError`` if the caller isn't the addressee."""
    row = await session.get(Friendship, friendship_id)
    if row is None or row.status != "pending":
        return None
    if row.addressee_id != user_id:
        raise PermissionError("only the addressee can accept this request")
    row.status = "accepted"
    row.responded_at = _now()
    return row


async def decline_or_cancel(
    session: AsyncSession, *, friendship_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Decline a request (addressee) or cancel one you sent (requester) — deletes the pending
    row. Returns True if a row was removed. Raises ``PermissionError`` for an unrelated user."""
    row = await session.get(Friendship, friendship_id)
    if row is None:
        return False
    if user_id not in (row.requester_id, row.addressee_id):
        raise PermissionError("not your friend request")
    await session.delete(row)
    return True


async def remove_friend(
    session: AsyncSession, *, user_id: uuid.UUID, other_id: uuid.UUID
) -> bool:
    """Remove an accepted friendship (either side). Returns True if one was removed."""
    row = await _row_for_pair(session, user_id, other_id)
    if row is None:
        return False
    await session.delete(row)
    return True


async def are_friends(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID
) -> bool:
    """True iff ``a`` and ``b`` are accepted friends."""
    row = await _row_for_pair(session, a, b)
    return row is not None and row.status == "accepted"


async def friend_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """The user ids accepted as friends of ``user_id``."""
    rows = (
        await session.execute(
            select(Friendship.requester_id, Friendship.addressee_id).where(
                Friendship.status == "accepted",
                or_(
                    Friendship.requester_id == user_id,
                    Friendship.addressee_id == user_id,
                ),
            )
        )
    ).all()
    return [a if b == user_id else b for a, b in rows]


async def friend_ids_among(
    session: AsyncSession, *, user_id: uuid.UUID, candidate_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of ``candidate_ids`` are accepted friends of ``user_id`` (for list badges)."""
    if not candidate_ids:
        return set()
    cands = set(candidate_ids)
    rows = (
        await session.execute(
            select(Friendship.requester_id, Friendship.addressee_id).where(
                Friendship.status == "accepted",
                or_(
                    and_(Friendship.requester_id == user_id, Friendship.addressee_id.in_(cands)),
                    and_(Friendship.addressee_id == user_id, Friendship.requester_id.in_(cands)),
                ),
            )
        )
    ).all()
    return {a if b == user_id else b for a, b in rows}


async def friend_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    """How many accepted friends a user has."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Friendship)
            .where(
                Friendship.status == "accepted",
                or_(
                    Friendship.requester_id == user_id,
                    Friendship.addressee_id == user_id,
                ),
            )
        )
        or 0
    )


async def incoming_requests(session: AsyncSession, user_id: uuid.UUID) -> list[Friendship]:
    """Pending requests addressed to the user (most-recent-first)."""
    return list(
        (
            await session.scalars(
                select(Friendship)
                .where(Friendship.addressee_id == user_id, Friendship.status == "pending")
                .order_by(Friendship.created_at.desc())
            )
        ).all()
    )


async def outgoing_requests(session: AsyncSession, user_id: uuid.UUID) -> list[Friendship]:
    """Pending requests the user has sent."""
    return list(
        (
            await session.scalars(
                select(Friendship)
                .where(Friendship.requester_id == user_id, Friendship.status == "pending")
                .order_by(Friendship.created_at.desc())
            )
        ).all()
    )


async def friendship_state(
    session: AsyncSession, *, viewer: uuid.UUID, target: uuid.UUID
) -> tuple[str, uuid.UUID | None]:
    """The viewer's relation to ``target`` for the Friend button: returns ``(state, row_id)``
    where state ∈ ``self|friends|incoming|outgoing|none`` (incoming = target asked the viewer,
    outgoing = viewer asked the target). ``row_id`` is the friendship id when one exists."""
    if viewer == target:
        return "self", None
    row = await _row_for_pair(session, viewer, target)
    if row is None:
        return "none", None
    if row.status == "accepted":
        return "friends", row.id
    # pending
    return ("outgoing" if row.requester_id == viewer else "incoming"), row.id
