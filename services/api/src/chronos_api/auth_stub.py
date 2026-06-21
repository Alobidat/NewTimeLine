"""Identity stub — the single bridge to Phase-4 auth (ADR-0025).

Every interaction write (comment / reaction / source-vote / user event-link) resolves its
actor through :func:`get_actor`. **Today** it returns a fixed dev/anonymous actor UUID
(``settings.dev_actor_id``) so interaction is testable end-to-end without an auth stack.

**Phase 4** replaces *only the body* of :func:`get_actor` with the real OIDC session lookup
(read the bearer/session, resolve/auto-provision the ``users`` row, return its id). No router
or schema changes are needed — they all depend on this one function.
"""

from __future__ import annotations

import uuid

from chronos_core.settings import get_settings
from fastapi import HTTPException, status


def get_actor() -> uuid.UUID:
    """Resolve the current user id for an interaction write.

    Stub: returns the configured dev/anonymous actor. Phase 4 swaps the body for OIDC.
    """
    settings = get_settings()
    try:
        return uuid.UUID(settings.dev_actor_id)
    except ValueError as exc:  # misconfigured env → fail loudly rather than write a bad id
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "dev_actor_id is not a valid UUID",
        ) from exc
