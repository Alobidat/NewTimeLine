"""User account ORM models — real accounts for Phase-4 auth (ADR-0026).

Three tables implement the accounts layer designed in docs/data-model.md §3.5:

- :class:`User`         — the account: handle, display name, primary email + verified flag,
  reputation, prefs. Auto-provisioned on first social login.
- :class:`UserIdentity` — a linked social identity (Google/Apple/Facebook/X/…). One user may
  have many; ``UNIQUE(provider, provider_sub)`` keys a provider account to exactly one user
  (account linkage: a second provider whose email matches an existing user links to it).
- :class:`UserAgreement` — a recorded acceptance of a versioned Terms/use/privacy document.
  Writes are gated on a *current*-version acceptance (see ``require_verified_actor``).

The interaction tables (comments/reactions/source_votes) and the graph (`event_relations`)
still store the actor as a plain ``user_id``/``created_by`` value — no hard FK was added in
0005, and we keep it that way so the slices stay decoupled; GDPR purge fans out explicitly
(see :mod:`chronos_core.accounts_repo`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from chronos_core.db.base import Base
from chronos_core.models.mixins import UuidPk


class User(UuidPk, Base):
    """A user account. Auto-provisioned on first social login (no registration form)."""

    __tablename__ = "users"

    handle: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    # Profile picture URL (the OAuth ``picture`` claim, captured at login). Nullable —
    # email-login users have none and the client renders an initials avatar instead.
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    # Free-text profile bio (nullable). Audience-gated via prefs['privacy']['bio'].
    bio: Mapped[str | None] = mapped_column(Text)
    # Primary email (from a linked identity); nullable until a provider asserts one.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    # True once a provider asserted a verified email OR the user confirmed an emailed code.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reputation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # True for AI-user (bot persona) accounts. Indexed so "is this a bot?" is a cheap predicate
    # without joining ``bot_profiles``; keeps bots distinguishable from humans in any metric.
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    prefs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserIdentity(UuidPk, Base):
    """A social identity linked to a :class:`User` (account linkage across providers)."""

    __tablename__ = "user_identities"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # google|apple|facebook|twitter|...
    provider_sub: Mapped[str] = mapped_column(String(255), nullable=False)  # OIDC 'sub'
    email: Mapped[str | None] = mapped_column(String(320))  # provider-asserted (may be a relay)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("provider", "provider_sub", name="uq_user_identities_provider_sub"),
        Index("ix_user_identities_user", "user_id"),
    )


class UserAgreement(Base):
    """A user's acceptance of a versioned Terms/acceptable-use/privacy document.

    PK on (user_id, version) → one acceptance row per version. Writes are gated on a row for
    the *current* ``agreement_version`` (Settings); a version bump re-prompts every user.
    """

    __tablename__ = "user_agreements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
