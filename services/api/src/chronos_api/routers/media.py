"""Media serving — hand the client a usable URL for an event's media.

Locally-stored binaries (archive/pin) are streamed straight from the object store (the API
can reach MinIO internally even though the browser cannot); external/link media redirects to
its origin. This is the simple serving path; signed-URL/CDN delivery is a later optimization.
"""

from __future__ import annotations

import asyncio
import uuid

from chronos_core import objectstore
from chronos_core.models.media import Media
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{media_id}/raw")
async def media_raw(media_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Stream a stored media binary, or redirect to its external origin."""
    media = await session.get(Media, media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    if media.status == "stored" and media.storage_key:
        data = await asyncio.to_thread(objectstore.get_bytes, media.storage_key)
        return Response(content=data, media_type=media.mime or "application/octet-stream")
    target = media.embed_url or media.source_url
    if target:
        return RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "no servable media")
