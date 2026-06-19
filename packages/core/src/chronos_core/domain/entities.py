"""Pure entity helpers (no I/O): name normalization + relation-weight scoring.

``name_key`` is the case/whitespace-insensitive resolution key used to merge entity
mentions that lack a Wikidata QID ("United  States" and "united states" → one row).
``relation_weight`` turns the count of shared entities (and whether the shared set
includes a location) into the ``event_relations.weight`` the linker stores.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def entity_name_key(name: str) -> str:
    """Normalize an entity name to its resolution key: trimmed, collapsed-space, lowercase."""
    return _WS.sub(" ", name.strip()).lower()


def relation_weight(shared_entities: int, *, shares_location: bool = False) -> float:
    """Score an edge from how much two events have in common.

    More shared entities → stronger; a shared *location* gets a bonus because the product
    anchors chains on place (the "US ↔ Iran" promise). Saturates near 1.0.
    """
    if shared_entities <= 0:
        return 0.0
    base = 1.0 - 0.6 ** shared_entities  # 1→0.4, 2→0.64, 3→0.78, …
    if shares_location:
        base = base + (1.0 - base) * 0.5  # halve the remaining gap to 1.0
    return round(base, 4)
