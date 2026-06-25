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
from chronos_core.models.media import Media, MediaVariant
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.deps import get_session

router = APIRouter(prefix="/media", tags=["media"])

# Descriptive UA so upstreams (Wikimedia etc.) don't 403 the proxy fetch.
_UA = "ChronosBot/0.1 (+https://github.com/Alobidat/NewTimeLine) media-proxy"

# Headers worth forwarding from the upstream so the browser can stream/seek video.
_PASSTHROUGH = ("content-range", "accept-ranges", "content-length", "cache-control")


def _ranged_bytes(data: bytes, mime: str, range_header: str | None) -> Response:
    """Serve in-memory ``data`` honouring a ``Range`` request (HTML5 <video> needs 206)."""
    total = len(data)
    headers = {"accept-ranges": "bytes"}
    if range_header and range_header.startswith("bytes="):
        spec = range_header.removeprefix("bytes=").split(",")[0]
        start_s, _, end_s = spec.partition("-")
        try:
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else total - 1
        except ValueError:
            start, end = 0, total - 1
        start = max(0, start)
        end = min(end, total - 1)
        if start > end:
            start, end = 0, total - 1
        chunk = data[start : end + 1]
        headers["content-range"] = f"bytes {start}-{end}/{total}"
        return Response(
            content=chunk, media_type=mime,
            status_code=status.HTTP_206_PARTIAL_CONTENT, headers=headers,
        )
    return Response(content=data, media_type=mime, headers=headers)


async def _proxy_stream(target: str, mime: str | None, range_header: str | None) -> Response:
    """Stream an external origin through the API, forwarding ``Range`` both ways so the
    browser's <video> element can range-request/seek (Wikimedia upload hosts support 206).

    Streamed (not buffered): the bytes flow chunk-by-chunk, so a 100 MB clip never lands in
    the API's memory. Falls back to a plain redirect if the upstream can't be opened."""
    req_headers = {"User-Agent": _UA}
    if range_header:
        req_headers["Range"] = range_header
    client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None), follow_redirects=True)
    try:
        upstream = await client.send(
            client.build_request("GET", target, headers=req_headers), stream=True
        )
    except Exception:
        await client.aclose()
        return RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        return RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    headers = {
        k: upstream.headers[k] for k in _PASSTHROUGH if k in upstream.headers
    }
    headers.setdefault("accept-ranges", "bytes")
    media_type = upstream.headers.get("content-type") or mime or "application/octet-stream"

    async def _body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        _body(), status_code=upstream.status_code, media_type=media_type, headers=headers
    )


@router.get("/{media_id}/raw")
async def media_raw(
    media_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
):
    """Serve media bytes with HTTP Range support: slice the stored binary, else **proxy-stream**
    the external origin (forwarding Range so the browser's <video> can seek). Range support is
    what lets HTML5 video play at all on the web — a 200 full-body response often won't."""
    media = await session.get(Media, media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    range_header = request.headers.get("range")
    # Prefer the web-playable mp4 variant (transcode agent) so the clip plays cross-browser; fall
    # back to the original binary, then to proxying the external origin.
    variant = await session.scalar(
        select(MediaVariant).where(
            MediaVariant.media_id == media_id,
            MediaVariant.rendition == "web",
            MediaVariant.status == "stored",
        )
    )
    if variant is not None:
        data = await asyncio.to_thread(objectstore.get_bytes, variant.storage_key)
        return _ranged_bytes(data, variant.mime or "video/mp4", range_header)
    if media.status == "stored" and media.storage_key:
        data = await asyncio.to_thread(objectstore.get_bytes, media.storage_key)
        return _ranged_bytes(data, media.mime or "application/octet-stream", range_header)
    target = media.embed_url or media.source_url
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no servable media")
    return await _proxy_stream(target, media.mime, range_header)


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
