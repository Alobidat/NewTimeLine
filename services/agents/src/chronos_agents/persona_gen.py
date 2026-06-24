"""Persona generator: create AI-user accounts with LLM-written personas + stock-photo avatars.

Generates personas in batches via the local LLM (``chronos_core.llm`` router → Ollama), each a
diverse fictional character with a name, handle, bio, 3-5 interests drawn from the canonical
taxonomy, interest weights, and a tone. Every persona gets a monotonic integer ``seed`` so a
re-run is idempotent (a seed that already has a bot is skipped). Avatars are assigned via
:mod:`chronos_agents.avatars`.

Run:
    python -m chronos_agents.run persona-gen --count 20
"""

from __future__ import annotations

import logging
import random

import httpx
from chronos_core import bots_repo, config_service
from chronos_core.db import session_scope
from chronos_core.llm import build_router
from chronos_core.models.bot import BotProfile
from sqlalchemy import func, select

from chronos_agents._json import extract_json_array
from chronos_agents.avatars import assign_avatar
from chronos_agents.bots import INTERESTS

log = logging.getLogger("chronos.agents.persona_gen")
AGENT = "persona-gen"

_SYSTEM = (
    "You invent fictional social-media personas for a world-events short-video app. "
    "Return ONLY a JSON array (no prose, no code fences). Each element: "
    '{"display_name": string, "handle": string (lowercase a-z0-9 and hyphens, 3-20 chars), '
    '"bio": string (<=160 chars), "interests": string[] (3-5 chosen from the ALLOWED list), '
    '"interest_weights": object mapping each chosen interest to a number summing to ~1.0, '
    '"tone": string (one or two words, e.g. "wry", "earnest", "analytical", "hype")}. '
    "Make them DIVERSE in geography, age, gender, profession, and viewpoint. "
    "Do NOT use real, living, identifiable people. Do NOT reuse any handle in the AVOID list."
)


def _clean_persona(raw: dict, seed: int) -> dict | None:
    """Validate + normalise one LLM persona dict. Returns a clean dict or None if unusable."""
    name = (raw.get("display_name") or "").strip()
    if not name:
        return None
    # Keep only interests in the canonical taxonomy; default if the model went off-script.
    interests = [i for i in (raw.get("interests") or []) if i in INTERESTS][:5]
    if not interests:
        interests = random.Random(seed).sample(list(INTERESTS), 3)
    weights_raw = raw.get("interest_weights") or {}
    weights = {i: float(weights_raw.get(i, 0) or 0) for i in interests}
    total = sum(weights.values())
    if total <= 0:
        weights = {i: 1.0 / len(interests) for i in interests}  # uniform fallback
    else:
        weights = {i: round(w / total, 4) for i, w in weights.items()}
    handle = (raw.get("handle") or "").strip().lower() or None
    return {
        "display_name": name[:128],
        "handle": handle,
        "bio": (raw.get("bio") or "").strip()[:160] or None,
        "interests": interests,
        "interest_weights": weights,
        "tone": (raw.get("tone") or "").strip()[:64] or None,
    }


async def _existing_handles(session) -> list[str]:
    from chronos_core.models.user import User

    rows = (await session.execute(select(User.handle).where(User.is_bot.is_(True)))).scalars().all()
    return list(rows)


async def _next_seed(session) -> int:
    cur = await session.scalar(select(func.max(BotProfile.seed)))
    return int(cur or 0) + 1


async def generate_personas(count: int, *, batch: int | None = None) -> dict:
    """Generate ``count`` AI users (personas + avatars). Returns counts."""
    totals = {"requested": count, "created": 0, "skipped": 0, "failed": 0}
    async with session_scope() as session:
        await config_service.ensure_defaults(session)
        batch = batch or int(await config_service.get(session, "bots.persona_gen.batch_size", 20))
        router = await build_router(session)
        seed = await _next_seed(session)
        avoid = set(await _existing_handles(session))

        try:
            async with httpx.AsyncClient() as client:
                remaining = count
                while remaining > 0:
                    n = min(batch, remaining)
                    # Spread interests: nudge each batch toward a rotating focus so the roster
                    # isn't all the same few topics (the model still chooses freely).
                    focus = INTERESTS[(seed // max(batch, 1)) % len(INTERESTS)]
                    user_prompt = (
                        f"Generate {n} personas. Lean a few of them toward '{focus}'. "
                        f"ALLOWED interests: {', '.join(INTERESTS)}. "
                        f"AVOID these handles: {', '.join(sorted(avoid)[:60]) or '(none)'}."
                    )
                    try:
                        resp = await router.complete(
                            system=_SYSTEM, user=user_prompt, max_tokens=2048
                        )
                        items = extract_json_array(resp.text)
                    except Exception:
                        log.warning("persona batch failed (seed≈%s)", seed, exc_info=True)
                        totals["failed"] += n
                        remaining -= n
                        continue

                    for raw in items[:n]:
                        if await bots_repo.bot_exists_for_seed(session, seed):
                            totals["skipped"] += 1
                            seed += 1
                            continue
                        persona = _clean_persona(raw if isinstance(raw, dict) else {}, seed)
                        if persona is None:
                            totals["failed"] += 1
                            seed += 1
                            continue
                        try:
                            user, _profile = await bots_repo.create_bot(
                                session,
                                seed=seed,
                                handle=persona["handle"],
                                display_name=persona["display_name"],
                                avatar_url=None,
                                persona=persona["bio"],
                                interests=persona["interests"],
                                interest_weights=persona["interest_weights"],
                                tone=persona["tone"],
                            )
                        except Exception:
                            log.warning("create_bot failed (seed=%s)", seed, exc_info=True)
                            totals["failed"] += 1
                            seed += 1
                            continue
                        # Avatar (best-effort; bot stays usable without one).
                        await assign_avatar(client, session, user, seed)
                        avoid.add(user.handle)
                        await session.commit()
                        totals["created"] += 1
                        seed += 1
                    remaining -= n
        finally:
            await router.aclose()

    log.info("persona-gen: %s", totals)
    return totals
