"""Per-profile privacy settings (stored in ``users.prefs['privacy']``, ADR plan).

Each profile field carries a **minimum audience** that may view it; a post carries a
**default audience** applied when the user doesn't pick one. Audience semantics:

- ``public``    — anyone (incl. anonymous)
- ``followers`` — the user + their followers
- ``friends``   — the user + accepted friends
- ``only_me``   — the user alone (field audiences only; a post is at least friends-visible)

**Absent ⇒ public** (backward-compatible): a user who never set privacy is fully public, so
existing/agent/bot accounts are unaffected until they opt into a tighter audience.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

FieldAudience = Literal["public", "followers", "friends", "only_me"]
PostAudience = Literal["public", "followers", "friends"]


class PrivacySettings(BaseModel):
    """The viewable-audience for each profile facet + the default audience for new posts."""

    bio: FieldAudience = "public"
    posts: FieldAudience = "public"
    followers: FieldAudience = "public"
    following: FieldAudience = "public"
    interactions: FieldAudience = "public"
    default_post_audience: PostAudience = "public"

    @classmethod
    def from_prefs(cls, prefs: dict | None) -> "PrivacySettings":
        """Read settings out of a user's ``prefs`` JSONB (absent → all-public defaults)."""
        raw = (prefs or {}).get("privacy") or {}
        # Tolerate unknown/old keys: validate only the known fields, fall back to defaults.
        return cls.model_validate({k: raw[k] for k in cls.model_fields if k in raw})

    def merged_into(self, prefs: dict | None) -> dict:
        """Return a copy of ``prefs`` with this privacy block written under ``privacy``."""
        out = dict(prefs or {})
        out["privacy"] = self.model_dump()
        return out
