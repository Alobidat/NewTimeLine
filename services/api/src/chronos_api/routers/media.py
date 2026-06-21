"""Media serving — hand the client a usable URL for an event's media.

Locally-stored binaries (archive/pin) are streamed straight from the object store (the API
can reach MinIO internally even though the browser cannot); external/link media redirects to
its origin. This is the simple serving path; signed-URL/CDN delivery is a later optimization.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
from chronos_core import objectstore
from chronos_core.models.media import Media
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session

router = APIRouter(prefix="/media", tags=["media"])

# Descriptive UA so upstreams (Wikimedia etc.) don't 403 the proxy fetch.
_UA = "ChronosBot/0.1 (+https://github.com/Alobidat/NewTimeLine) media-proxy"


@router.get("/{media_id}/raw")
async def media_raw(media_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Serve media bytes: stream the stored binary, else **proxy-fetch** the external origin
    (so the browser always gets bytes regardless of cross-origin/UA restrictions)."""
    media = await session.get(Media, media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    if media.status == "stored" and media.storage_key:
        data = await asyncio.to_thread(objectstore.get_bytes, media.storage_key)
        return Response(content=data, media_type=media.mime or "application/octet-stream")
    target = media.embed_url or media.source_url
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no servable media")
    try:
        async with httpx.AsyncClient(headers={"User-Agent": _UA}) as client:
            resp = await client.get(target, follow_redirects=True, timeout=20.0)
            resp.raise_for_status()
        ctype = resp.headers.get("content-type") or media.mime or "application/octet-stream"
        return Response(content=resp.content, media_type=ctype)
    except Exception:
        # Last resort: let the browser try the origin directly.
        return RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/{media_id}/thumb")
async def media_thumb(media_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Serve the pre-generated JPEG thumbnail for an image media item.

    Falls back to a redirect to ``/raw`` for non-image media (video, embed) or items
    whose thumbnail hasn't been generated yet (e.g. still pending fetch).
    """
    media = await session.get(Media, media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    if media.thumbnail_key:
        data = await asyncio.to_thread(objectstore.get_bytes, media.thumbnail_key)
        return Response(content=data, media_type="image/jpeg")
    return RedirectResponse(
        f"/media/{media_id}/raw", status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
