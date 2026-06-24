"""Interest → free-video search queries for the AI-user post engine.

Each canonical interest (see :data:`chronos_agents.bots.INTERESTS`) maps to a handful of concrete
search phrases the free-video providers (Wikimedia Commons, NASA, stock APIs) search with. The
post engine picks a bot's interest weighted by its ``interest_weights``, then a query from here.

Phrases lean toward terms that actually return freely-licensed footage (B-roll, archival,
public-domain agency footage) rather than copyrighted broadcast clips.
"""

from __future__ import annotations

from chronos_agents.bots import INTERESTS

INTEREST_QUERIES: dict[str, list[str]] = {
    "sports": ["marathon running", "olympic athletics", "cycling race", "football match",
               "swimming competition", "rock climbing"],
    "science": ["laboratory experiment", "microscope cells", "chemistry reaction",
                "physics demonstration", "DNA sequencing", "particle accelerator"],
    "news": ["city traffic timelapse", "protest march", "press conference",
             "skyline aerial", "harbor cargo ship"],
    "politics": ["parliament building", "flag waving", "voting ballot box",
                 "capitol government", "diplomatic summit"],
    "finance": ["stock exchange trading floor", "wall street", "city financial district",
                "bank building", "money counting", "gold bars"],
    "tech": ["robot arm factory", "data center servers", "circuit board",
             "drone flying", "3d printer", "solar panels"],
    "history": ["ancient ruins", "world war archival", "old city footage",
                "historical monument", "vintage film"],
    "culture": ["street festival", "traditional dance", "art gallery",
                "music concert", "food market"],
    "nature": ["ocean waves", "forest wildlife", "mountain landscape",
               "waterfall", "coral reef", "volcano eruption"],
    "space": ["rocket launch", "spacewalk", "mars rover", "earth from space",
              "nebula galaxy", "moon landing"],
    "health": ["hospital corridor", "surgery operating room", "running exercise",
               "healthy food vegetables", "medical research lab"],
    "travel": ["aerial coastline", "city timelapse night", "mountain hiking trail",
               "desert dunes", "tropical beach"],
}

# Every interest must have queries (the engine relies on it).
assert set(INTEREST_QUERIES) >= set(INTERESTS), "INTEREST_QUERIES missing an interest"


def queries_for(interest: str) -> list[str]:
    """Search phrases for an interest (empty list if unknown)."""
    return INTEREST_QUERIES.get(interest, [])
