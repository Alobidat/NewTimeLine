# `chronos_core.auth` — Phase-4 accounts & auth (ADR-0026)

Provider-agnostic social login, signed-JWT sessions, email verification, and the DB-side
account logic for real accounts. Mirrors the LLM provider registry (ADR-0014): the enabled
provider set + client id/secret/scopes are **config/Settings**, so adding a provider is
config, not code.

## Layout
| Module | Responsibility |
|--------|----------------|
| `jwt.py` | Tiny HS256 JWT encode/decode on the stdlib (no PyJWT dependency). |
| `session.py` | Issue/verify the session JWT (`sub`, email-verified, agreement version). |
| `email.py` | Pluggable `EmailSender` (SMTP or console stub) + short signed verify codes. |
| `providers/base.py` | `AuthProvider` abstraction + PKCE; pure `extract_claims` seam. |
| `providers/oidc_providers.py` | Google / Apple / Facebook / X (Twitter) adapters. |
| `providers/oauth.py` | The only HTTP I/O: authorize URL, token exchange, userinfo. |
| `providers/registry.py` | Builds enabled adapters from `auth.providers` config + secrets. |

Account persistence (provision/link, agreement, GDPR export/purge) is
`chronos_core.accounts_repo`. API endpoints live in `services/api` (`routers/auth.py`,
`routers/account.py`) and the session→user resolution + write gate are
`chronos_api.auth_stub.get_actor` / `require_verified_actor`.

## Config & secrets
- **Secrets (env/Settings):** `jwt_secret`, `jwt_ttl_seconds`, `auth_<provider>_client_secret`,
  `smtp_*`.
- **Toggles (Config Service):** `auth.providers` (enabled + client_id + scopes),
  `auth.redirect_base`, `auth.agreement_version`, `auth.agreement_url`,
  `auth.require_email_verified`.

Safe dev defaults: providers ship **disabled with empty client_ids**, so a fresh box boots
with no providers and `/auth/providers` returns `[]`.

## Provider verification hardening (later)
`extract_claims` is a **pure** mapping (unit-tested with respx-mocked HTTP). JWKS signature
verification of OIDC `id_token`s is the documented next hardening step (a network/JWKS call);
the claim extraction is structured to stay pure so that change is isolated.
