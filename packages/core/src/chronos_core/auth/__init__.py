"""Phase-4 auth core (ADR-0026): JWT sessions, email verification, and the provider registry.

- :mod:`jwt`       — stdlib HS256 encode/decode (no extra dependency).
- :mod:`session`   — issue/verify the signed-JWT session the API hands clients after login.
- :mod:`email`     — pluggable email sender + short signed verification codes.
- :mod:`providers` — provider-agnostic OAuth2/OIDC (Google/Apple/Facebook/X), config-driven.

The DB-side account logic (provision/link/agreement/GDPR) lives in
:mod:`chronos_core.accounts_repo`.
"""
