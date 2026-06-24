"""Chronos Event API — FastAPI app factory.

Public, read-mostly API for the timeline/map/event-detail/sub-timeline. Writes (create)
exist for manual/admin use; the agent pipeline writes via chronos_core.repository directly.
Anonymous reads are allowed (ADR-0007); auth-gated writes arrive in Phase 4.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from chronos_core import config_service
from chronos_core.db import session_scope
from chronos_core.settings import get_settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chronos_api.routers import (
    account,
    admin,
    admin_bots,
    auth,
    entities,
    events,
    feed,
    health,
    interactions,
    links,
    media,
    search,
    social,
    timeline,
    upload,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed Config Service defaults on startup (idempotent)."""
    async with session_scope() as session:
        await config_service.ensure_defaults(session)
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="Chronos Event API",
        version="0.1.0",
        summary="Timeline, map, and event data for NewTimeLine.",
        lifespan=lifespan,
    )
    # Dev CORS is permissive so the Flutter web client can call us; tighten per env later.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment == "dev" else [],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(timeline.router)
    app.include_router(search.router)
    app.include_router(entities.router)
    app.include_router(media.router)
    app.include_router(interactions.router)
    app.include_router(links.router)
    app.include_router(social.router)
    app.include_router(feed.router)
    app.include_router(upload.router)
    app.include_router(auth.router)
    app.include_router(account.router)
    app.include_router(admin.router)
    app.include_router(admin_bots.router)
    return app


app = create_app()
