"""Search endpoint — the entry point to the dig (event-presentation.md §5, ADR-0022).

A search both **reads existing data and triggers live collection**:
- ``GET /search`` fans the query out across events + actors (person/org) + places, returns a
  faceted :class:`SearchResults`, and enqueues an on-demand ``collect`` job onto the Phase-3b
  Redis run-queue (mirroring the admin run-now) so the corpus keeps expanding.
- ``GET /search/stream`` is a public SSE channel that emits *newly-collected* matching events
  as the collector publishes them, so the client can show "showing N results, collecting more…".
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import redis as redislib
from chronos_core import config_service
from chronos_core.config_spec import SPEC_BY_KEY
from chronos_core.db import session_scope
from chronos_core.run_queue import push_job
from chronos_core.schemas.graph import SearchResults
from chronos_core.settings import get_settings
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session
from chronos_api.graph_queries import (
    ACTOR_KINDS,
    PLACE_KINDS,
    search_entities_by_kinds,
    search_events,
    search_users,
)

log = logging.getLogger("chronos.api.search")

router = APIRouter(prefix="/search", tags=["search"])

_COLLECT_COMMAND = "collect"


def _subject_text(q: str | None, location: str | None, actor: str | None) -> str:
    """Combined subject string (keyword + actor + location), space-joined, deduped —
    mirrors ``sources.base.SubjectQuery.text`` so the stream filter matches the collector."""
    seen: list[str] = []
    for p in (q, actor, location):
        if p and p not in seen:
            seen.append(p)
    return " ".join(seen).strip()


def _collect_args(q: str | None, location: str | None, actor: str | None) -> dict:
    """The job args the on-demand collector reads (``--keyword/--location/--actor``)."""
    args: dict = {}
    if q:
        args["keyword"] = q
    if location:
        args["location"] = location
    if actor:
        args["actor"] = actor
    return args


async def _cfg(session: AsyncSession, key: str):
    """Config value with the spec default as fallback (works before the DB is seeded)."""
    return await config_service.get(session, key, SPEC_BY_KEY[key].default)


def _enqueue_collect(args: dict) -> bool:
    """Push a ``collect`` job onto the Redis run-queue (same mechanism as admin run-now).
    Returns whether the job was enqueued; never raises into the request path."""
    try:
        r = redislib.from_url(get_settings().redis_url)
        try:
            push_job(r, _COLLECT_COMMAND, args)
        finally:
            r.close()
        return True
    except Exception:
        log.warning("search: failed to enqueue collect job", exc_info=True)
        return False


@router.get("", response_model=SearchResults)
async def search(
    q: str | None = Query(default=None, description="free text; matches title, entity, or author"),
    location: str | None = Query(default=None, description="place facet (country/city/area)"),
    actor: str | None = Query(default=None, description="actor name(s)"),
    author: str | None = Query(default=None, description="creator handle / display name"),
    media: str | None = Query(default=None, description="'video' restricts to clip-hero events"),
    t0: float | None = Query(default=None, description="from year (signed; negative=BC)"),
    t1: float | None = Query(default=None, description="to year (signed)"),
    category: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    collect: bool = Query(default=True, description="also enqueue a live-collection job"),
    session: AsyncSession = Depends(get_session),
) -> SearchResults:
    """Faceted search (events + actors + places + creators) that also triggers live collection.

    Returns DB matches immediately and, when enabled, enqueues an on-demand ``collect`` job
    so the corpus expands; the client follows ``/search/stream`` to refresh as results land.
    """
    # The free-text term feeds every facet; location/actor/author narrow the matching facets.
    # Queries run sequentially: a single AsyncSession is not safe for concurrent use.
    term = q or actor or author or location
    facet_limit = int(await _cfg(session, "search.facet_limit"))

    events = await search_events(
        session, q=term, t0=t0, t1=t1, category=category, media=media, limit=limit
    )
    actors = await search_entities_by_kinds(
        session, q=(actor or q), kinds=ACTOR_KINDS, limit=facet_limit
    )
    places = await search_entities_by_kinds(
        session, q=(location or q), kinds=PLACE_KINDS, limit=facet_limit
    )
    # Creators facet: who posted — searchable by handle or display name (e.g. "newsreel").
    creators = await search_users(session, q=(author or q), limit=facet_limit)

    subject = _subject_text(q, location, actor)
    collecting = False
    if collect and subject and bool(await _cfg(session, "search.live_collection.enabled")):
        collecting = await asyncio.to_thread(
            _enqueue_collect, _collect_args(q, location, actor)
        )

    return SearchResults(
        subject=subject,
        collecting=collecting,
        events=events,
        actors=actors,
        places=places,
        creators=creators,
    )


def _sse(event: str, data) -> str:
    """Format a single Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/stream")
async def search_stream(
    request: Request,
    q: str | None = Query(default=None, description="free text; matches title or entity name"),
    location: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    t0: float | None = Query(default=None),
    t1: float | None = Query(default=None),
    category: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> StreamingResponse:
    """Public SSE feed of *newly-collected* events matching a search subject (ADR-0022).

    Mirrors the admin stream's polling pattern: every tick it re-runs the search restricted
    to events created since the connection opened and emits each new match as an ``event``
    frame, plus a periodic ``status`` frame carrying the running count. The client renders
    "showing N results, collecting more…" and refreshes live as the collector publishes.
    The stream is stateless — the client reconnects automatically on drop.
    """
    term = q or actor or location

    async def gen():
        seen: set[str] = set()
        started = datetime.now(UTC)
        async with session_scope() as session:
            poll = int(await _cfg(session, "search.stream.poll_seconds"))
            max_secs = int(await _cfg(session, "search.stream.max_seconds"))
        emitted = 0
        try:
            while not await request.is_disconnected():
                if (datetime.now(UTC) - started).total_seconds() > max_secs:
                    break
                async with session_scope() as session:
                    rows = await search_events(
                        session, q=term, t0=t0, t1=t1, category=category,
                        since=started, limit=limit,
                    )
                new = [r for r in rows if str(r.id) not in seen]
                for r in new:
                    seen.add(str(r.id))
                    emitted += 1
                    yield _sse("event", r.model_dump())
                yield _sse("status", {"emitted": emitted, "collecting": True})
                await asyncio.sleep(poll)
        except asyncio.CancelledError:
            pass  # client disconnected
        except Exception:
            log.exception("search SSE stream error")
        finally:
            yield _sse("status", {"emitted": emitted, "collecting": False})

    return StreamingResponse(gen(), media_type="text/event-stream")
