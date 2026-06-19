"""Search endpoint — the entry point to the dig: find events by free text (title or a
linked entity name) within an optional signed-year range."""

from __future__ import annotations

from chronos_core.schemas.event import EventRead
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session
from chronos_api.graph_queries import search_events

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[EventRead])
async def search(
    q: str | None = Query(default=None, description="free text; matches title or entity name"),
    t0: float | None = Query(default=None, description="from year (signed; negative=BC)"),
    t1: float | None = Query(default=None, description="to year (signed)"),
    category: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[EventRead]:
    """Find events to anchor a dig, by title/entity text and time range."""
    return await search_events(session, q=q, t0=t0, t1=t1, category=category, limit=limit)
