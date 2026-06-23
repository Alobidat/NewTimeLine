"""Auth endpoints: social login, email verify, agreement (ADR-0026).

Flow: GET /auth/providers (offerable set) → GET /auth/{provider}/login (authorize URL + PKCE)
→ GET|POST /auth/{provider}/callback (exchange code → verify → auto-provision/link → issue a
session JWT). Email verify (/auth/verify/request|confirm) covers providers that don't assert a
verified email. Agreement (/auth/agreement[/accept]) records the versioned acceptance the
write gate (``require_verified_actor``) checks. Reads are open; only the gate blocks writes.
"""

from __future__ import annotations

from chronos_core import accounts_repo, config_service
from chronos_core.auth import email as email_mod
from chronos_core.auth import session as auth_session
from chronos_core.auth.providers import get_provider, list_enabled_ids, make_pkce
from chronos_core.auth.providers import oauth
from chronos_core.schemas.auth import (
    AgreementAccept,
    AgreementInfo,
    AgreementStatus,
    AuthCallback,
    DevLoginStart,
    DevLoginVerify,
    LoginStart,
    ProviderInfo,
    ProviderList,
    SessionToken,
    VerifyConfirm,
    VerifyIssued,
    VerifyRequest,
)
from chronos_core.settings import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.auth_stub import get_actor
from chronos_api.deps import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


def _callback_uri(request: Request, provider: str, redirect_base: str) -> str:
    base = (redirect_base or str(request.base_url)).rstrip("/")
    return f"{base}/auth/{provider}/callback"


async def _issue_session(session: AsyncSession, user) -> SessionToken:
    """Mint a session JWT for a user + report whether they still owe an agreement."""
    version = await config_service.get(session, "auth.agreement_version", "")
    accepted = bool(version) and await accounts_repo.has_accepted(session, user.id, version)
    token = auth_session.issue(
        user.id,
        email_verified=user.email_verified,
        agreement_version=version if accepted else None,
    )
    return SessionToken(
        access_token=token,
        user_id=user.id,
        email_verified=user.email_verified,
        needs_agreement=bool(version) and not accepted,
    )


# --- providers + login ----------------------------------------------------------------


@router.get("/providers", response_model=ProviderList)
async def providers(session: AsyncSession = Depends(get_session)) -> ProviderList:
    """The login providers a client may offer (enabled + fully configured). May be empty.

    Also reports whether the self-contained dev email-code login is available so the client
    can offer it when no OAuth provider is configured (or alongside one in pre-launch)."""
    ids = await list_enabled_ids(session)
    dev_login = bool(await config_service.get(session, "auth.dev_login_enabled", True))
    return ProviderList(
        providers=[ProviderInfo(id=p) for p in ids], dev_login=dev_login
    )


@router.get("/{provider}/login", response_model=LoginStart)
async def login(
    provider: str, request: Request, session: AsyncSession = Depends(get_session)
) -> LoginStart:
    """Begin auth-code+PKCE: return the authorize URL + the verifier the client keeps."""
    adapter = await get_provider(session, provider)
    if adapter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"provider not available: {provider}")
    redirect_base = await config_service.get(session, "auth.redirect_base", "")
    redirect_uri = _callback_uri(request, provider, redirect_base)
    pkce = make_pkce()
    state = make_pkce().verifier  # an opaque, unguessable state value
    url = oauth.build_authorize_url(
        adapter, redirect_uri=redirect_uri, challenge=pkce, state=state
    )
    return LoginStart(
        provider=provider, authorize_url=url, state=state, code_verifier=pkce.verifier
    )


async def _complete_login(
    provider: str, data: AuthCallback, request: Request, session: AsyncSession
) -> SessionToken:
    adapter = await get_provider(session, provider)
    if adapter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"provider not available: {provider}")
    redirect_base = await config_service.get(session, "auth.redirect_base", "")
    redirect_uri = _callback_uri(request, provider, redirect_base)
    try:
        claims = await oauth.resolve_claims(
            adapter, code=data.code, redirect_uri=redirect_uri, verifier=data.code_verifier
        )
    except Exception as exc:  # noqa: BLE001 - provider/network failure → 502
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"provider exchange failed: {exc}") from exc
    if not claims.provider_sub:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "provider returned no subject id")
    user, _created = await accounts_repo.provision_from_identity(
        session,
        provider=claims.provider,
        provider_sub=claims.provider_sub,
        email=claims.email,
        email_verified=claims.email_verified,
        name=claims.name,
    )
    return await _issue_session(session, user)


@router.post("/{provider}/callback", response_model=SessionToken)
async def callback_post(
    provider: str,
    data: AuthCallback,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> SessionToken:
    """Exchange the auth code → verify → auto-provision/link → issue a session JWT."""
    return await _complete_login(provider, data, request, session)


@router.get("/{provider}/callback", response_model=SessionToken)
async def callback_get(
    provider: str,
    request: Request,
    code: str,
    state: str,
    code_verifier: str,
    session: AsyncSession = Depends(get_session),
) -> SessionToken:
    """GET form of the callback (for providers/clients that redirect with query params)."""
    data = AuthCallback(code=code, state=state, code_verifier=code_verifier)
    return await _complete_login(provider, data, request, session)


# --- dev email-code login -------------------------------------------------------------


async def _require_dev_login(session: AsyncSession) -> None:
    """404 the dev-login endpoints unless ``auth.dev_login_enabled`` is set."""
    if not bool(await config_service.get(session, "auth.dev_login_enabled", True)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dev login is disabled")


@router.post("/dev/start", response_model=VerifyIssued)
async def dev_login_start(
    data: DevLoginStart, session: AsyncSession = Depends(get_session)
) -> VerifyIssued:
    """Begin self-contained email-code sign-in: email a one-time code to the address. No
    session needed (this is how an anonymous user signs in). Non-prod returns the code so the
    flow is exercisable without a live mailbox."""
    await _require_dev_login(session)
    if "@" not in data.email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email")
    code = email_mod.make_code(data.email)
    email_mod.get_sender().send(
        data.email, "Your NewTimeLine sign-in code", f"Your sign-in code is: {code}"
    )
    dev_code = code if get_settings().environment != "prod" else None
    return VerifyIssued(sent=True, dev_code=dev_code)


@router.post("/dev/verify", response_model=SessionToken)
async def dev_login_verify(
    data: DevLoginVerify, session: AsyncSession = Depends(get_session)
) -> SessionToken:
    """Complete email-code sign-in: validate the code → provision/link a verified user for the
    email → issue a session JWT. The email is proven by the code, so the user is email-verified."""
    await _require_dev_login(session)
    if not email_mod.check_code(data.code, data.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired code")
    user, _created = await accounts_repo.provision_from_identity(
        session,
        provider="email",
        provider_sub=data.email.lower(),
        email=data.email,
        email_verified=True,
        name=None,
    )
    return await _issue_session(session, user)


# --- email verification ---------------------------------------------------------------


@router.post("/verify/request", response_model=VerifyIssued)
async def verify_request(
    data: VerifyRequest, session: AsyncSession = Depends(get_session)
) -> VerifyIssued:
    """Email a verification code to the caller. Providers that assert a verified email don't
    need this; X/Facebook (no verified email) do before write access."""
    if "@" not in data.email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email")
    code = email_mod.make_code(data.email)
    sender = email_mod.get_sender()
    sender.send(
        data.email,
        "Verify your NewTimeLine email",
        f"Your verification code is: {code}",
    )
    # In non-prod we return the code so the flow is exercisable without a live mailbox.
    dev_code = code if get_settings().environment != "prod" else None
    return VerifyIssued(sent=True, dev_code=dev_code)


@router.post("/verify/confirm", response_model=SessionToken)
async def verify_confirm(
    data: VerifyConfirm,
    session: AsyncSession = Depends(get_session),
    actor=Depends(get_actor),
) -> SessionToken:
    """Confirm an emailed code for the signed-in caller → mark verified + re-issue a session."""
    if not email_mod.check_code(data.code, data.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired code")
    user = await accounts_repo.mark_email_verified(session, actor, data.email)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in before verifying")
    return await _issue_session(session, user)


# --- agreement ------------------------------------------------------------------------


@router.get("/agreement", response_model=AgreementInfo)
async def agreement(session: AsyncSession = Depends(get_session)) -> AgreementInfo:
    """The current agreement version + a pointer to its text."""
    version = await config_service.get(session, "auth.agreement_version", "")
    url = await config_service.get(session, "auth.agreement_url", "")
    return AgreementInfo(version=version, url=url)


@router.get("/agreement/status", response_model=AgreementStatus)
async def agreement_status(
    session: AsyncSession = Depends(get_session), actor=Depends(get_actor)
) -> AgreementStatus:
    """Whether the signed-in caller has accepted the current agreement version."""
    version = await config_service.get(session, "auth.agreement_version", "")
    accepted = bool(version) and await accounts_repo.has_accepted(session, actor, version)
    return AgreementStatus(version=version, accepted=accepted)


@router.post("/agreement/accept", response_model=SessionToken)
async def agreement_accept(
    data: AgreementAccept,
    session: AsyncSession = Depends(get_session),
    actor=Depends(get_actor),
) -> SessionToken:
    """Record acceptance of the current agreement version → re-issue a session reflecting it."""
    from chronos_core.models.user import User

    current = await config_service.get(session, "auth.agreement_version", "")
    if not current or data.version != current:
        raise HTTPException(status.HTTP_409_CONFLICT, "agreement version is not current")
    user = await session.get(User, actor)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in before accepting")
    await accounts_repo.accept_agreement(session, actor, current)
    return await _issue_session(session, user)
