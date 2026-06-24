"""Account-update DTO (PATCH /account/me).

A partial update: only the fields *present in the request* are changed (tracked via pydantic's
``model_fields_set``), so a client can edit just the bio, or just the privacy block, without
clobbering the rest. ``display_name``/``bio``/``avatar_url`` accept ``null`` to clear.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chronos_core.schemas.privacy import PrivacySettings


class AccountUpdate(BaseModel):
    """Editable profile fields + privacy settings; all optional (PATCH semantics)."""

    display_name: str | None = Field(default=None, max_length=128)
    bio: str | None = Field(default=None, max_length=2000)
    avatar_url: str | None = Field(default=None, max_length=1024)
    privacy: PrivacySettings | None = None
