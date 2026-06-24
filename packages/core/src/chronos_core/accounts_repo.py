"""Account write/read helpers: provisioning, agreement, GDPR purge + export (ADR-0026).

Pure DB logic shared by the auth + account routers. Covers:

- **first-login auto-provision + account linkage** (:func:`provision_from_identity`): an
  identity (provider, sub) resolves to its existing user; else, if the asserted email matches
  an existing user, the identity is *linked* to it; else a fresh ``users`` row is created.
- **email verification** (:func:`mark_email_verified`) and **agreement** acceptance/lookup.
- **GDPR self-service**: :func:`export_user` (portable JSON of everything we hold) and
  :func:`purge_user` (irreversible cascade across identities, agreements, comments, reactions,
  votes, user-authored event-links — plus best-effort object-store deletion of the user's
  uploads). The interaction tables key the actor by a plain ``user_id``/``created_by`` value
  (no FK — see migration 0005/0006), so the fan-out is explicit here, not a DB cascade.

Callers commit. Object-store deletion is best-effort (logged, never blocks the purge).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core.models.bot import BotProfile
from chronos_core.models.friendship import Friendship
from chronos_core.models.interaction import Comment, CommentReaction, Reaction, SourceVote
from chronos_core.models.media import EventMedia
from chronos_core.models.relation import EventRelation
from chronos_core.models.social import ActivityLog, Bookmark, Follow, Promote
from chronos_core.models.user import User, UserAgreement, UserIdentity

log = logging.getLogger("chronos.accounts")

_HANDLE_RE = re.compile(r"[^a-z0-9]+")


def _derive_handle(seed: str, suffix: str) -> str:
    """A URL-safe handle from a name/email seed + a short unique suffix."""
    base = _HANDLE_RE.sub("", (seed or "user").split("@")[0].lower())[:24] or "user"
    return f"{base}-{suffix[:6]}"


# --- provisioning + linkage -----------------------------------------------------------


async def get_user_by_identity(
    session: AsyncSession, provider: str, provider_sub: str
) -> User | None:
    """Resolve the user behind a (provider, sub), or ``None``."""
    ident = (
        await session.scalars(
            select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.provider_sub == provider_sub,
            )
        )
    ).first()
    if ident is None:
        return None
    return await session.get(User, ident.user_id)


async def provision_from_identity(
    session: AsyncSession,
    *,
    provider: str,
    provider_sub: str,
    email: str | None,
    email_verified: bool,
    name: str | None,
    avatar: str | None = None,
) -> tuple[User, bool]:
    """Resolve/create the user for a verified provider identity. Returns (user, created).

    - Existing (provider, sub) → that user (and refresh verified email if newly asserted).
    - Else email matches an existing user → **link** the identity to it (account linkage).
    - Else → auto-provision a new ``users`` row + identity (first social login).
    """
    existing = await get_user_by_identity(session, provider, provider_sub)
    if existing is not None:
        if email_verified and email and not existing.email_verified:
            existing.email = existing.email or email.lower()
            existing.email_verified = True
        if avatar and not existing.avatar_url:
            existing.avatar_url = avatar  # backfill a picture once a provider supplies one
        return existing, False

    user: User | None = None
    if email:
        user = (
            await session.scalars(select(User).where(User.email == email.lower()))
        ).first()

    created = False
    if user is None:
        user = User(
            handle=_derive_handle(name or email or "user", uuid.uuid4().hex),
            display_name=name,
            avatar_url=avatar,
            email=email.lower() if email else None,
            email_verified=bool(email and email_verified),
        )
        session.add(user)
        await session.flush()
        created = True
    elif email_verified and email and not user.email_verified:
        user.email_verified = True

    session.add(
        UserIdentity(
            user_id=user.id,
            provider=provider,
            provider_sub=provider_sub,
            email=email.lower() if email else None,
        )
    )
    await session.flush()
    return user, created


async def mark_email_verified(session: AsyncSession, user_id: uuid.UUID, email: str) -> User | None:
    """Record a user's email as verified (after an emailed-code confirm)."""
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.email = email.lower()
    user.email_verified = True
    return user


async def update_account(session: AsyncSession, user_id: uuid.UUID, data) -> User | None:
    """Apply a partial profile update. Only fields *present in the request* (``model_fields_set``)
    are changed; ``privacy`` is read-modify-written into ``prefs``. Caller commits."""
    user = await session.get(User, user_id)
    if user is None:
        return None
    fields = data.model_fields_set
    if "display_name" in fields:
        user.display_name = data.display_name
    if "bio" in fields:
        user.bio = data.bio
    if "avatar_url" in fields:
        user.avatar_url = data.avatar_url
    if "privacy" in fields and data.privacy is not None:
        # Reassign (not mutate) so SQLAlchemy detects the JSONB change.
        user.prefs = data.privacy.merged_into(user.prefs)
    await session.flush()
    return user


# --- agreement ------------------------------------------------------------------------


async def has_accepted(session: AsyncSession, user_id: uuid.UUID, version: str) -> bool:
    """True iff the user has accepted the given agreement version."""
    return (await session.get(UserAgreement, (user_id, version))) is not None


async def accept_agreement(
    session: AsyncSession, user_id: uuid.UUID, version: str
) -> UserAgreement:
    """Record acceptance of an agreement version (idempotent per version)."""
    existing = await session.get(UserAgreement, (user_id, version))
    if existing is not None:
        return existing
    row = UserAgreement(user_id=user_id, version=version)
    session.add(row)
    await session.flush()
    return row


# --- GDPR: export ---------------------------------------------------------------------


async def export_user(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """A portable JSON archive of everything we hold about the caller (GDPR download)."""
    user = await session.get(User, user_id)
    if user is None:
        return {}
    sub = str(user_id)

    identities = (
        await session.scalars(select(UserIdentity).where(UserIdentity.user_id == user_id))
    ).all()
    agreements = (
        await session.scalars(select(UserAgreement).where(UserAgreement.user_id == user_id))
    ).all()
    comments = (
        await session.scalars(select(Comment).where(Comment.user_id == user_id))
    ).all()
    reactions = (
        await session.scalars(select(Reaction).where(Reaction.user_id == user_id))
    ).all()
    votes = (
        await session.scalars(select(SourceVote).where(SourceVote.user_id == user_id))
    ).all()
    links = (
        await session.scalars(
            select(EventRelation).where(EventRelation.created_by == sub)
        )
    ).all()
    media_links = (
        await session.scalars(select(EventMedia).where(EventMedia.added_by == sub))
    ).all()
    follows = (
        await session.scalars(select(Follow).where(Follow.user_id == user_id))
    ).all()
    promotes = (
        await session.scalars(select(Promote).where(Promote.user_id == user_id))
    ).all()
    bookmarks = (
        await session.scalars(select(Bookmark).where(Bookmark.user_id == user_id))
    ).all()
    friendships = (
        await session.scalars(
            select(Friendship).where(
                or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id)
            )
        )
    ).all()
    # Bot persona (only present for AI-user accounts; cascades off ``users`` on purge).
    bot_profile = await session.get(BotProfile, user_id) if user.is_bot else None

    return {
        "schema": "chronos.user_export.v1",
        "user": {
            "id": sub,
            "handle": user.handle,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "bio": user.bio,
            "email": user.email,
            "email_verified": user.email_verified,
            "reputation": user.reputation,
            "is_bot": user.is_bot,
            "prefs": user.prefs,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "bot_profile": (
            {
                "interests": bot_profile.interests,
                "interest_weights": bot_profile.interest_weights,
                "tone": bot_profile.tone,
                "persona": bot_profile.persona,
                "posts_count": bot_profile.posts_count,
                "interactions_count": bot_profile.interactions_count,
            }
            if bot_profile
            else None
        ),
        "identities": [
            {"provider": i.provider, "provider_sub": i.provider_sub, "email": i.email,
             "linked_at": i.linked_at.isoformat() if i.linked_at else None}
            for i in identities
        ],
        "agreements": [
            {"version": a.version, "accepted_at": a.accepted_at.isoformat()} for a in agreements
        ],
        "comments": [
            {"id": str(c.id), "event_id": str(c.event_id), "parent_id": str(c.parent_id) if c.parent_id else None,
             "body": c.body, "status": c.status, "created_at": c.created_at.isoformat()}
            for c in comments
        ],
        "reactions": [
            {"event_id": str(r.event_id), "kind": r.kind,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in reactions
        ],
        "source_votes": [
            {"event_id": str(v.event_id), "source_id": str(v.source_id), "verdict": v.verdict}
            for v in votes
        ],
        "event_links": [
            {"src_event": str(l.src_event), "dst_event": str(l.dst_event), "kind": l.kind}
            for l in links
        ],
        "media_links": [
            {"event_id": str(m.event_id), "media_id": str(m.media_id), "role": m.role}
            for m in media_links
        ],
        "follows": [
            {"target_type": f.target_type, "target_id": str(f.target_id)} for f in follows
        ],
        "promotes": [
            {"target_type": p.target_type, "target_id": str(p.target_id), "value": p.value}
            for p in promotes
        ],
        "bookmarks": [
            {"event_id": str(b.event_id),
             "created_at": b.created_at.isoformat() if b.created_at else None}
            for b in bookmarks
        ],
        "friendships": [
            {"requester_id": str(f.requester_id), "addressee_id": str(f.addressee_id),
             "status": f.status,
             "created_at": f.created_at.isoformat() if f.created_at else None}
            for f in friendships
        ],
    }


# --- GDPR: purge ----------------------------------------------------------------------


async def purge_user(session: AsyncSession, user_id: uuid.UUID, *, objectstore=None) -> dict[str, int]:
    """Irreversibly delete the user and ALL their data. Returns a per-table delete count.

    Cascade (explicit because interactions key the actor by a plain value, not an FK):
      identities, agreements (FK ON DELETE CASCADE off ``users``) + comments, reactions,
      source_votes, user-authored event-links (``created_by``), and the user's media links
      (``added_by``). Best-effort: object-store keys of media the user uploaded are deleted
      (logged, never blocks the purge). Caller commits.
    """
    sub = str(user_id)
    counts: dict[str, int] = {}

    # Best-effort object-store cleanup for media the user added (before dropping the links).
    if objectstore is not None:
        await _purge_user_objects(session, sub, objectstore)

    counts["comments"] = (
        await session.execute(delete(Comment).where(Comment.user_id == user_id))
    ).rowcount or 0
    counts["reactions"] = (
        await session.execute(delete(Reaction).where(Reaction.user_id == user_id))
    ).rowcount or 0
    counts["source_votes"] = (
        await session.execute(delete(SourceVote).where(SourceVote.user_id == user_id))
    ).rowcount or 0
    counts["event_links"] = (
        await session.execute(delete(EventRelation).where(EventRelation.created_by == sub))
    ).rowcount or 0
    counts["media_links"] = (
        await session.execute(delete(EventMedia).where(EventMedia.added_by == sub))
    ).rowcount or 0
    counts["follows"] = (
        await session.execute(delete(Follow).where(Follow.user_id == user_id))
    ).rowcount or 0
    counts["promotes"] = (
        await session.execute(delete(Promote).where(Promote.user_id == user_id))
    ).rowcount or 0
    counts["activity"] = (
        await session.execute(delete(ActivityLog).where(ActivityLog.user_id == user_id))
    ).rowcount or 0
    counts["bookmarks"] = (
        await session.execute(delete(Bookmark).where(Bookmark.user_id == user_id))
    ).rowcount or 0
    counts["comment_reactions"] = (
        await session.execute(delete(CommentReaction).where(CommentReaction.user_id == user_id))
    ).rowcount or 0
    counts["friendships"] = (
        await session.execute(
            delete(Friendship).where(
                or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id)
            )
        )
    ).rowcount or 0
    # identities + agreements cascade off users; deleting the user removes them.
    counts["user"] = (
        await session.execute(delete(User).where(User.id == user_id))
    ).rowcount or 0
    return counts


async def _purge_user_objects(session: AsyncSession, sub: str, objectstore) -> None:
    """Delete object-store binaries/thumbnails for media the user uploaded (best-effort)."""
    from chronos_core.models.media import Media

    rows = (
        await session.execute(
            select(Media.storage_key, Media.thumbnail_key)
            .join(EventMedia, EventMedia.media_id == Media.id)
            .where(EventMedia.added_by == sub)
        )
    ).all()
    for storage_key, thumb_key in rows:
        for key in (storage_key, thumb_key):
            if not key:
                continue
            try:
                objectstore.delete(key)
            except Exception as exc:  # noqa: BLE001 - never block a GDPR purge on storage
                log.warning("object-store delete failed for %s: %s", key, exc)
