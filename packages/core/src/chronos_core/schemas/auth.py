"""API DTOs for the auth / account surface (ADR-0026)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# Plain str (not pydantic EmailStr) so we don't add the email-validator dependency; the
# format is sanity-checked at the router. Verification mail proves real ownership anyway.
EmailStr = str

__all__ = [
    "ProviderInfo",
    "ProviderList",
    "LoginStart",
    "AuthCallback",
    "SessionToken",
    "DevLoginStart",
    "DevLoginVerify",
    "VerifyRequest",
    "VerifyConfirm",
    "VerifyIssued",
    "AgreementInfo",
    "AgreementAccept",
    "AgreementStatus",
    "UserMe",
    "PurgeResult",
]


class ProviderInfo(BaseModel):
    """One offerable login provider (enabled + configured)."""

    id: str


class ProviderList(BaseModel):
    """The set of providers a client may offer the user."""

    providers: list[ProviderInfo] = Field(default_factory=list)
    # Self-contained email-code sign-in is available (no external OAuth provider). The client
    # shows an email login form when true — see auth.dev_login_enabled.
    dev_login: bool = False


class LoginStart(BaseModel):
    """Where to send the user + the PKCE verifier the client keeps for the callback."""

    provider: str
    authorize_url: str
    state: str
    code_verifier: str  # the client stores this and presents it on /callback


class AuthCallback(BaseModel):
    """Callback payload: the code + state + the PKCE verifier issued at login start. A web
    client also echoes the ``redirect_uri`` it used at /login so the token exchange matches."""

    code: str
    state: str
    code_verifier: str
    redirect_uri: str | None = None


class SessionToken(BaseModel):
    """The signed-JWT session issued after a successful login/verification."""

    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    email_verified: bool
    needs_agreement: bool  # True if the user still owes a current-version acceptance
    # The resolved account, so the client has the avatar/handle immediately without relying on
    # a follow-up /account/me refresh (which can silently fail). The mobile AuthSession reads it.
    user: "UserMe | None" = None


class DevLoginStart(BaseModel):
    """Begin dev email-code sign-in: email a one-time code to this address."""

    email: EmailStr


class DevLoginVerify(BaseModel):
    """Complete dev email-code sign-in: the email + the code that was sent to it."""

    email: EmailStr
    code: str


class VerifyRequest(BaseModel):
    """Request an email-verification code be sent."""

    email: EmailStr


class VerifyIssued(BaseModel):
    """Acknowledge a verification request. In non-prod the code is returned for testing."""

    sent: bool
    dev_code: str | None = None


class VerifyConfirm(BaseModel):
    """Confirm a verification code emailed to the caller."""

    email: EmailStr
    code: str


class AgreementInfo(BaseModel):
    """The current agreement version + where its text lives."""

    version: str
    url: str


class AgreementAccept(BaseModel):
    """Accept a specific agreement version (must equal the current one)."""

    version: str


class AgreementStatus(BaseModel):
    """Whether the caller has accepted the current agreement."""

    version: str
    accepted: bool


class UserMe(BaseModel):
    """The caller's own account (GET /account/me)."""

    id: uuid.UUID
    handle: str
    display_name: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    email_verified: bool
    reputation: int
    prefs: dict = Field(default_factory=dict)
    created_at: datetime


class PurgeResult(BaseModel):
    """Per-table delete counts from a GDPR account purge."""

    deleted: dict[str, int]


# SessionToken forward-references UserMe (defined above it); resolve it now.
SessionToken.model_rebuild()
