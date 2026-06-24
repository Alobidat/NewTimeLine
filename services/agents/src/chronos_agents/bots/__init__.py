"""AI-user (bot persona) engines: persona generation, posting, interaction, scheduling.

The canonical **interest taxonomy** lives here because every bot module references it: the
persona generator draws each character's interests from it, ``topics`` maps each interest to
free-video search queries, and the post engine picks a topic weighted by the bot's interests.
"""

from __future__ import annotations

# The fixed interest vocabulary. Keep in sync with ``topics.INTEREST_QUERIES`` (every interest
# here must have queries there) and the category strings the feed already uses.
INTERESTS: tuple[str, ...] = (
    "sports",
    "science",
    "news",
    "politics",
    "finance",
    "tech",
    "history",
    "culture",
    "nature",
    "space",
    "health",
    "travel",
)
