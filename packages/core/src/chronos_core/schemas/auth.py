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


class LoginStart(BaseModel):
    """Where to send the user + the PKCE verifier the client keeps for the callback."""

    provider: str
    authorize_url: str
    state: str
    code_verifier: str  # the client stores this and presents it on /callback


class AuthCallback(BaseModel):
    """Callback payload: the code + state + the PKCE verifier issued at login start."""

    code: str
    state: str
    code_verifier: str


class SessionToken(BaseModel):
    """The signed-JWT session issued after a successful login/verification."""

    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    email_verified: bool
    needs_agreement: bool  # True if the user still owes a current-version acceptance


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
    email: str | None = None
    email_verified: bool
    reputation: int
    prefs: dict = Field(default_factory=dict)
    created_at: datetime


class PurgeResult(BaseModel):
    """Per-table delete counts from a GDPR account purge."""

    deleted: dict[str, int]
