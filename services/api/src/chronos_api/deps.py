"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

from chronos_core.db import session_scope
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped DB session (commits on success, rolls back on error)."""
    async with session_scope() as session:
        yield session
