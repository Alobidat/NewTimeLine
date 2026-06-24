"""Concrete provider adapters: Google, Apple, Facebook, X (Twitter) (ADR-0026).

Each declares its endpoints + a **pure** ``extract_claims``. Google + Apple are OIDC: identity
travels in the ``id_token`` (a JWT) returned from the token exchange, so ``extract_claims``
reads its claims (decoded by the OIDC-conformant token-response shape the callback passes in).
Facebook + X are OAuth2 with a userinfo/API call.

Adding a provider = add an adapter class here + a config entry; the registry wires it up.
JWKS signature verification of the id_token is the documented hardening step (a network/JWKS
call); the claim *extraction* is kept pure + testable, with HTTP mocked via respx in tests.
"""

from __future__ import annotations

import base64
import json

from chronos_core.auth.providers.base import AuthProvider, ProviderClaims


def _decode_jwt_claims(token: str) -> dict:
    """Decode (without verifying) the claims segment of a JWT id_token. Returns {} on failure.

    The token comes from the provider's own token endpoint over TLS; signature verification
    against the provider JWKS is a documented hardening step (issue a network call). For claim
    extraction we read the payload — kept pure so it is unit-testable.
    """
    try:
        payload_seg = token.split(".")[1]
        pad = "=" * (-len(payload_seg) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_seg + pad))
    except Exception:  # noqa: BLE001 - any malformed token → no claims
        return {}


class GoogleProvider(AuthProvider):
    id = "google"
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    userinfo_url = "https://openidconnect.googleapis.com/v1/userinfo"
    uses_id_token = True

    def extract_claims(self, token_response: dict, userinfo: dict | None) -> ProviderClaims:
        claims = _decode_jwt_claims(token_response.get("id_token", "")) if token_response.get("id_token") else {}
        if not claims and userinfo:
            claims = userinfo
        return ProviderClaims(
            provider=self.id,
            provider_sub=str(claims.get("sub", "")),
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified", False)),
            name=claims.get("name") or claims.get("given_name"),
            avatar=claims.get("picture"),  # standard OIDC picture URL (Google sets it)
        )


class AppleProvider(AuthProvider):
    id = "apple"
    authorize_url = "https://appleid.apple.com/auth/authorize"
    token_url = "https://appleid.apple.com/auth/token"
    userinfo_url = None  # Apple returns everything in the id_token
    uses_id_token = True

    def authorize_params(self, *, redirect_uri, challenge, state):
        params = super().authorize_params(redirect_uri=redirect_uri, challenge=challenge, state=state)
        # Apple requires form_post when name/email scopes are requested.
        params["response_mode"] = "form_post"
        return params

    def extract_claims(self, token_response: dict, userinfo: dict | None) -> ProviderClaims:
        claims = _decode_jwt_claims(token_response.get("id_token", ""))
        # Apple's email_verified arrives as the string "true"/"false" or a bool.
        ev = claims.get("email_verified", False)
        email_verified = ev is True or (isinstance(ev, str) and ev.lower() == "true")
        return ProviderClaims(
            provider=self.id,
            provider_sub=str(claims.get("sub", "")),
            email=claims.get("email"),
            email_verified=email_verified,
            name=None,  # Apple only sends name on the very first authorization, via form fields
        )


class FacebookProvider(AuthProvider):
    id = "facebook"
    authorize_url = "https://www.facebook.com/v18.0/dialog/oauth"
    token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
    userinfo_url = "https://graph.facebook.com/me?fields=id,name,email,picture.type(large)"
    uses_id_token = False

    def extract_claims(self, token_response: dict, userinfo: dict | None) -> ProviderClaims:
        info = userinfo or {}
        # Facebook returns email only if the user granted it + verified it on FB's side; FB
        # does not expose a per-account verified flag, so we treat its email as UNVERIFIED and
        # require our own email verification before write access.
        # The picture is nested as picture.data.url (the type(large) variant requested above).
        picture = ((info.get("picture") or {}).get("data") or {}).get("url")
        return ProviderClaims(
            provider=self.id,
            provider_sub=str(info.get("id", "")),
            email=info.get("email"),
            email_verified=False,
            name=info.get("name"),
            avatar=picture,
        )


class TwitterProvider(AuthProvider):
    id = "twitter"
    authorize_url = "https://twitter.com/i/oauth2/authorize"
    token_url = "https://api.twitter.com/2/oauth2/token"
    userinfo_url = "https://api.twitter.com/2/users/me?user.fields=profile_image_url"
    uses_id_token = False

    def extract_claims(self, token_response: dict, userinfo: dict | None) -> ProviderClaims:
        # X (Twitter) v2 nests the user under "data" and does NOT return email by default →
        # always unverified; our emailed-code verification collects + confirms it.
        data = (userinfo or {}).get("data", {})
        return ProviderClaims(
            provider=self.id,
            provider_sub=str(data.get("id", "")),
            email=data.get("email"),
            email_verified=False,
            name=data.get("name") or data.get("username"),
            avatar=data.get("profile_image_url"),
        )


ADAPTERS: dict[str, type[AuthProvider]] = {
    GoogleProvider.id: GoogleProvider,
    AppleProvider.id: AppleProvider,
    FacebookProvider.id: FacebookProvider,
    TwitterProvider.id: TwitterProvider,
}
