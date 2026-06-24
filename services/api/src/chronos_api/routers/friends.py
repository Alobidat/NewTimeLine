"""Friends endpoints — explicit, mutual relationships via request + accept.

- POST   /friends/request?target_id=  — send (or auto-accept a reverse) request.
- POST   /friends/{id}/accept         — accept a pending request addressed to you.
- POST   /friends/{id}/decline        — decline (addressee) or cancel (requester) a request.
- DELETE /friends?target_id=          — remove an accepted friend.
- GET    /friends                     — your accepted friends (UserSummary).
- GET    /friends/requests            — your incoming + outgoing pending requests.
- GET    /friends/state?target_id=    — the viewer's relation to a user (for the Friend button).

Writes resolve through ``require_verified_actor``; ``state`` is a read (``get_actor``).
"""

from __future__ import annotations

import uuid

from chronos_core import friends_repo, social_repo
from chronos_core.schemas.friends import (
    FriendList,
    FriendRequestList,
    FriendRequestRead,
    FriendStateResult,
)
from chronos_core.schemas.social import UserSummary
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.auth_stub import get_actor, require_verified_actor
from chronos_api.deps import get_session

router = APIRouter(prefix="/friends", tags=["friends"])


async def _summaries(
    session: AsyncSession, ids: list[uuid.UUID], caller: uuid.UUID
) -> list[UserSummary]:
    users = await social_repo.users_by_ids(session, ids)
    followed = await social_repo.following_user_ids_among(
        session, user_id=caller, candidate_ids=ids
    )
    return [
        UserSummary(
            id=u.id, handle=u.handle, display_name=u.display_name,
            avatar_url=u.avatar_url, following=u.id in followed,
        )
        for uid in ids
        if (u := users.get(uid)) is not None
    ]


@router.post("/request", response_model=FriendStateResult, status_code=status.HTTP_201_CREATED)
async def send_request(
    target_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> FriendStateResult:
    """Send a friend request (auto-accepts if the target already requested you)."""
    try:
        row = await friends_repo.request_friend(session, requester=actor, addressee=target_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await session.flush()
    state, fid = await friends_repo.friendship_state(session, viewer=actor, target=target_id)
    return FriendStateResult(target_id=target_id, state=state, friendship_id=fid)


@router.post("/{friendship_id}/accept", response_model=FriendStateResult)
async def accept(
    friendship_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> FriendStateResult:
    """Accept a pending request addressed to you."""
    try:
        row = await friends_repo.accept_request(
            session, friendship_id=friendship_id, user_id=actor
        )
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no pending request")
    other = row.requester_id if row.addressee_id == actor else row.addressee_id
    return FriendStateResult(target_id=other, state="friends", friendship_id=row.id)


@router.post("/{friendship_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline(
    friendship_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> None:
    """Decline a request addressed to you, or cancel one you sent."""
    try:
        await friends_repo.decline_or_cancel(
            session, friendship_id=friendship_id, user_id=actor
        )
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    target_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> None:
    """Remove an accepted friend (by their user id)."""
    await friends_repo.remove_friend(session, user_id=actor, other_id=target_id)


@router.get("", response_model=FriendList)
async def my_friends(
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> FriendList:
    """The caller's accepted friends."""
    ids = await friends_repo.friend_ids(session, actor)
    items = await _summaries(session, ids, actor)
    return FriendList(items=items, count=len(items))


@router.get("/requests", response_model=FriendRequestList)
async def my_requests(
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> FriendRequestList:
    """The caller's pending incoming + outgoing friend requests."""
    incoming = await friends_repo.incoming_requests(session, actor)
    outgoing = await friends_repo.outgoing_requests(session, actor)
    # The "other" user on each request.
    other_ids = [r.requester_id for r in incoming] + [r.addressee_id for r in outgoing]
    users = await social_repo.users_by_ids(session, other_ids)

    def _read(row, other_id, direction) -> FriendRequestRead | None:
        u = users.get(other_id)
        if u is None:
            return None
        return FriendRequestRead(
            friendship_id=row.id,
            user=UserSummary(
                id=u.id, handle=u.handle, display_name=u.display_name, avatar_url=u.avatar_url
            ),
            direction=direction,
            created_at=row.created_at,
        )

    return FriendRequestList(
        incoming=[r for row in incoming if (r := _read(row, row.requester_id, "incoming"))],
        outgoing=[r for row in outgoing if (r := _read(row, row.addressee_id, "outgoing"))],
    )


@router.get("/state", response_model=FriendStateResult)
async def state(
    target_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(get_actor),
) -> FriendStateResult:
    """The caller's friendship relation to a user (for the profile Friend button)."""
    st, fid = await friends_repo.friendship_state(session, viewer=actor, target=target_id)
    return FriendStateResult(target_id=target_id, state=st, friendship_id=fid)
