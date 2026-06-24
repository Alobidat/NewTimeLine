"""One-shot bulk bootstrap: stand up a roster of AI users and seed initial posts.

Generates ``count`` personas (with avatars) via :func:`persona_gen.generate_personas`, then has
each newly-created bot publish up to ``posts_per_bot`` clips **in-process** (not via the queue)
so the corpus fills predictably. Idempotent by persona seed — re-running tops up rather than
duplicating. After bootstrap, the steady-state ``bots-tick`` scheduler keeps the feed growing.

Run:
    python -m chronos_agents.run bots-bootstrap --count 300 --posts-per-bot 2
"""

from __future__ import annotations

import logging

from chronos_core import bots_repo
from chronos_core.db import session_scope

from chronos_agents.bots.post import persona_post
from chronos_agents.persona_gen import generate_personas

log = logging.getLogger("chronos.agents.bots.bootstrap")
AGENT = "bots-bootstrap"


async def bootstrap(count: int, *, posts_per_bot: int = 2) -> dict:
    """Create ``count`` personas, then seed ``posts_per_bot`` posts for each. Returns counts."""
    gen = await generate_personas(count)

    async with session_scope() as session:
        bots = await bots_repo.list_bots(session, limit=max(count * 2, 50))
        bot_ids = [str(u.id) for u, _b in bots]

    totals = {"personas": gen.get("created", 0), "posts": 0, "no_clip": 0, "rejected": 0}
    for uid in bot_ids:
        for _ in range(max(posts_per_bot, 0)):
            res = await persona_post(bot_id=uid)
            totals["posts"] += res.get("posted", 0)
            totals["no_clip"] += res.get("no_clip", 0)
            totals["rejected"] += res.get("rejected", 0)
            if not res.get("posted"):
                break  # nothing postable for this bot right now; move on
    log.info("bots-bootstrap: %s", totals)
    return totals
