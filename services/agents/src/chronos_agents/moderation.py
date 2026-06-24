"""LLM moderation (Phase 6) — an async safety pass over user posts + comments.

Posts auto-publish and comments are visible immediately; this agent reviews them out-of-band
with a local-or-cloud LLM (budget-aware router). On a policy hit it raises a ``moderation_flag``
for the admin queue, and — only when ``severity ≥ moderation.hold_threshold`` — *holds* the
content (event → ``pending``, comment → ``flagged``) so egregious cases disappear until an admin
acts. Everything is fire-and-forget from the API; a periodic ``moderate-pending`` batch backstops
any missed enqueues. Config: ``moderation.enabled``, ``hold_threshold``, ``max_tokens``.
"""

from __future__ import annotations

import json
import logging
import uuid

from chronos_core import config_service, moderation_repo
from chronos_core.db import session_scope
from chronos_core.llm import build_router
from chronos_core.models.enums import EventStatus
from chronos_core.models.event import Event
from chronos_core.models.interaction import Comment
from sqlalchemy import select

log = logging.getLogger("chronos.agents.moderation")

_SYSTEM = (
    "You are a content-moderation classifier for a social timeline app. Given a user post or "
    "comment, decide whether it violates a reasonable acceptable-use policy (hate, harassment, "
    "explicit sexual content, credible threats, spam/scam, illegal content). Respond with ONLY "
    'a JSON object: {"flag": <bool>, "reason": <short string>, "severity": <0-100 int>}. '
    "severity 0 = clearly fine, 100 = egregious. Be permissive about ordinary opinions, "
    "history, and strong language that isn't targeted hate/harassment."
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])


async def _classify(router, content: str, max_tokens: int) -> dict | None:
    """Run the LLM classifier; returns ``{flag, reason, severity}`` or None on failure."""
    try:
        resp = await router.complete(system=_SYSTEM, user=content[:4000], max_tokens=max_tokens)
        data = _extract_json(resp.text)
        return {
            "flag": bool(data.get("flag")),
            "reason": str(data.get("reason") or "")[:500],
            "severity": max(0, min(100, int(data.get("severity") or 0))),
        }
    except Exception:  # noqa: BLE001 - never let a model/parse error block content
        log.warning("moderation: classify failed", exc_info=True)
        return None


async def _review(session, router, *, target_type, target_id, content, hold_threshold) -> bool:
    """Classify one item; raise a flag (+ optionally hold) on a hit. Returns True if flagged."""
    verdict = await _classify(router, content, await _max_tokens(session))
    if verdict is None or not verdict["flag"]:
        return False
    await moderation_repo.raise_flag(
        session, target_type=target_type, target_id=target_id,
        reason=verdict["reason"], severity=verdict["severity"], source="llm",
    )
    if verdict["severity"] >= hold_threshold:
        if target_type == "event":
            ev = await session.get(Event, target_id)
            if ev is not None:
                ev.status = EventStatus.PENDING
        elif target_type == "comment":
            c = await session.get(Comment, target_id)
            if c is not None:
                c.status = "flagged"
    log.info("moderation: flagged %s %s (sev=%s)", target_type, target_id, verdict["severity"])
    return True


async def _max_tokens(session) -> int:
    return int(await config_service.get(session, "moderation.max_tokens", 200))


async def _hold_threshold(session) -> int:
    return int(await config_service.get(session, "moderation.hold_threshold", 90))


async def _enabled(session) -> bool:
    return bool(await config_service.get(session, "moderation.enabled", True))


async def moderate_event(event_id: str | None = None) -> dict:
    """Review one event (by id) or the most recent published user event."""
    async with session_scope() as session:
        if not await _enabled(session):
            return {"enabled": False}
        router = await build_router(session)
        ht = await _hold_threshold(session)
        try:
            event = (
                await session.get(Event, uuid.UUID(event_id)) if event_id else None
            )
            if event is None:
                return {"flagged": 0, "reason": "event not found"}
            text = f"{event.title}\n\n{event.summary or ''}"
            flagged = await _review(
                session, router, target_type="event", target_id=event.id,
                content=text, hold_threshold=ht,
            )
        finally:
            await router.aclose()
    return {"flagged": int(flagged)}


async def moderate_comment(comment_id: str | None = None) -> dict:
    """Review one comment by id."""
    async with session_scope() as session:
        if not await _enabled(session):
            return {"enabled": False}
        if not comment_id:
            return {"flagged": 0}
        router = await build_router(session)
        ht = await _hold_threshold(session)
        try:
            comment = await session.get(Comment, uuid.UUID(comment_id))
            if comment is None:
                return {"flagged": 0, "reason": "comment not found"}
            flagged = await _review(
                session, router, target_type="comment", target_id=comment.id,
                content=comment.body, hold_threshold=ht,
            )
        finally:
            await router.aclose()
    return {"flagged": int(flagged)}


async def moderate_pending(limit: int = 20) -> dict:
    """Batch backstop: review recent user events that have no moderation flag yet."""
    async with session_scope() as session:
        if not await _enabled(session):
            return {"enabled": False}
        router = await build_router(session)
        ht = await _hold_threshold(session)
        totals = {"reviewed": 0, "flagged": 0}
        try:
            rows = (
                await session.execute(
                    select(Event)
                    .where(Event.category == "user")
                    .order_by(Event.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            for event in rows:
                text = f"{event.title}\n\n{event.summary or ''}"
                flagged = await _review(
                    session, router, target_type="event", target_id=event.id,
                    content=text, hold_threshold=ht,
                )
                totals["reviewed"] += 1
                totals["flagged"] += int(flagged)
        finally:
            await router.aclose()
    log.info("moderate-pending: %s", totals)
    return totals
