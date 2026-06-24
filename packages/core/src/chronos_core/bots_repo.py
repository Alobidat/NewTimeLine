"""AI-user (bot persona) write/read helpers (ADR: AI users).

Pure DB logic over ``users`` (``is_bot``) + ``bot_profiles``, mirroring the style of
:mod:`chronos_core.accounts_repo` / :mod:`chronos_core.social_repo`. A bot is created by
reusing :func:`accounts_repo.provision_from_identity` with a synthetic ``provider="system"``
identity (so bots never touch a real login path), then flipping ``users.is_bot`` and inserting
the persona/behaviour row. Callers commit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core import accounts_repo
from chronos_core.models.bot import BotProfile
from chronos_core.models.user import User

# Synthetic identity provider for bot accounts (kept out of the real OAuth/email login paths).
BOT_PROVIDER = "system"


async def get_bot(session: AsyncSession, user_id: uuid.UUID) -> BotProfile | None:
    """The bot profile for a user id, or ``None`` if the user isn't a bot."""
    return await session.get(BotProfile, user_id)


async def bot_exists_for_seed(session: AsyncSession, seed: int) -> bool:
    """True iff a bot with this deterministic generation seed already exists (idempotency)."""
    n = await session.scalar(
        select(func.count()).select_from(BotProfile).where(BotProfile.seed == seed)
    )
    return (n or 0) > 0


async def create_bot(
    session: AsyncSession,
    *,
    seed: int,
    handle: str | None,
    display_name: str,
    avatar_url: str | None,
    persona: str | None,
    interests: list[str],
    interest_weights: dict[str, float],
    tone: str | None = None,
    post_cadence_min: int = 720,
    interact_cadence_min: int = 180,
    quality_threshold: int = 60,
    daily_post_cap: int = 3,
    daily_interact_cap: int = 30,
) -> tuple[User, BotProfile]:
    """Provision a bot user + its persona row. Idempotent per ``seed`` (returns the existing pair).

    The ``users`` row is created via :func:`accounts_repo.provision_from_identity` (handle
    derivation + identity row reuse) under a ``provider="system"`` identity keyed by ``seed``.
    ``handle`` is advisory: provisioning derives a unique handle from ``display_name``; if a
    specific handle is desired and free we set it after creation.
    """
    existing = await accounts_repo.get_user_by_identity(session, BOT_PROVIDER, f"bot:{seed}")
    if existing is not None:
        profile = await session.get(BotProfile, existing.id)
        if profile is not None:
            return existing, profile

    user, _created = await accounts_repo.provision_from_identity(
        session,
        provider=BOT_PROVIDER,
        provider_sub=f"bot:{seed}",
        email=None,
        email_verified=False,
        name=display_name,
        avatar=avatar_url,
    )
    user.is_bot = True
    if display_name:
        user.display_name = display_name
    if avatar_url:
        user.avatar_url = avatar_url
    # Honour a requested handle when it's free (else keep the derived-unique one).
    if handle and not await _handle_taken(session, handle, exclude=user.id):
        user.handle = handle

    profile = BotProfile(
        user_id=user.id,
        seed=seed,
        persona=persona,
        interests=interests,
        interest_weights=interest_weights,
        tone=tone,
        post_cadence_min=post_cadence_min,
        interact_cadence_min=interact_cadence_min,
        quality_threshold=quality_threshold,
        daily_post_cap=daily_post_cap,
        daily_interact_cap=daily_interact_cap,
    )
    session.add(profile)
    await session.flush()
    return user, profile


async def _handle_taken(session: AsyncSession, handle: str, *, exclude: uuid.UUID) -> bool:
    return (
        await session.scalar(
            select(func.count()).select_from(User).where(User.handle == handle, User.id != exclude)
        )
    ) > 0


async def list_bots(
    session: AsyncSession,
    *,
    enabled: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[tuple[User, BotProfile]]:
    """Bot (user, profile) pairs, newest first. Optional ``enabled`` filter."""
    stmt = (
        select(User, BotProfile)
        .join(BotProfile, BotProfile.user_id == User.id)
        .order_by(BotProfile.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if enabled is not None:
        stmt = stmt.where(BotProfile.enabled == enabled)
    rows = (await session.execute(stmt)).all()
    return [(u, b) for u, b in rows]


async def count_bots(session: AsyncSession, *, enabled: bool | None = None) -> int:
    stmt = select(func.count()).select_from(BotProfile)
    if enabled is not None:
        stmt = stmt.where(BotProfile.enabled == enabled)
    return await session.scalar(stmt) or 0


async def set_enabled(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    enabled: bool | None = None,
    posts_enabled: bool | None = None,
    interacts_enabled: bool | None = None,
) -> BotProfile | None:
    """Admin suspend / fine-grained gating. Only the provided flags change."""
    profile = await session.get(BotProfile, user_id)
    if profile is None:
        return None
    if enabled is not None:
        profile.enabled = enabled
    if posts_enabled is not None:
        profile.posts_enabled = posts_enabled
    if interacts_enabled is not None:
        profile.interacts_enabled = interacts_enabled
    return profile


async def update_config(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    post_cadence_min: int | None = None,
    interact_cadence_min: int | None = None,
    quality_threshold: int | None = None,
    daily_post_cap: int | None = None,
    daily_interact_cap: int | None = None,
) -> BotProfile | None:
    """Tune cadence/caps/threshold. Only the provided knobs change."""
    profile = await session.get(BotProfile, user_id)
    if profile is None:
        return None
    for field, value in (
        ("post_cadence_min", post_cadence_min),
        ("interact_cadence_min", interact_cadence_min),
        ("quality_threshold", quality_threshold),
        ("daily_post_cap", daily_post_cap),
        ("daily_interact_cap", daily_interact_cap),
    ):
        if value is not None:
            setattr(profile, field, value)
    return profile


async def bump_post_stats(session: AsyncSession, user_id: uuid.UUID, *, n: int = 1) -> None:
    """Record ``n`` posts: increment counter + stamp ``last_post_at`` (now)."""
    await session.execute(
        update(BotProfile)
        .where(BotProfile.user_id == user_id)
        .values(
            posts_count=BotProfile.posts_count + n,
            last_post_at=datetime.now(UTC),
        )
    )


async def bump_interact_stats(session: AsyncSession, user_id: uuid.UUID, *, n: int = 1) -> None:
    """Record ``n`` interactions: increment counter + stamp ``last_interact_at`` (now)."""
    await session.execute(
        update(BotProfile)
        .where(BotProfile.user_id == user_id)
        .values(
            interactions_count=BotProfile.interactions_count + n,
            last_interact_at=datetime.now(UTC),
        )
    )
