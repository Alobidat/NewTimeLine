"""FastAPI dependencies."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from chronos_core.db import session_scope
from chronos_core.settings import get_settings
from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("chronos.api.deps")


async def get_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped DB session (commits on success, rolls back on error)."""
    async with session_scope() as session:
        yield session


async def require_admin(authorization: str | None = Header(default=None)) -> str:
    """Admin gate (scaffold; full OIDC/RBAC in Phase 4).

    If ``admin_token`` is configured, require ``Authorization: Bearer <token>``. If it is
    unset in the ``dev`` environment, allow access (with a warning) so local work isn't
    blocked. Returns an actor label for audit trails.
    """
    settings = get_settings()
    if not settings.admin_token:
        if settings.environment == "dev":
            log.warning("admin API is OPEN (no admin_token set; dev only)")
            return "dev-admin"
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "admin token not configured")
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token != settings.admin_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid admin token")
    return "admin"
