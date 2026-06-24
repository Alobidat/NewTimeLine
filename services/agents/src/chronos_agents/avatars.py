"""License-clean profile pictures for AI users.

Each bot gets one portrait **downloaded into the object store** (durable, doesn't leak our user
count, and license is recorded on the ``media`` row) and its ``users.avatar_url`` pointed at the
same ``/media/{id}/raw`` route the feed serves media from.

Source selection (license-clean both ways):
- If a Pexels API key is configured (``bots.sources.pexels.api_key``) → a real **curated stock
  portrait** under the free Pexels License (the user's chosen avatar style).
- Else (keyless dev) → a free portrait from ``randomuser.me`` (free to use; 200 distinct faces),
  deterministically picked by the persona seed.

The downloaded bytes are validated as a decodable image before storage. Any failure is non-fatal
— the bot is simply left without ``avatar_url`` and the client renders its initials avatar.
"""

from __future__ import annotations

import hashlib
import io
import logging

import httpx
from chronos_core import config_service, objectstore
from chronos_core.domain.thumbnails import make_thumbnail
from chronos_core.models.media import Media
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("chronos.agents.avatars")

_PEXELS_PORTRAIT = "https://api.pexels.com/v1/search"


def _is_image(data: bytes) -> bool:
    """True iff ``data`` decodes as an image (guards against bot-block HTML pages, etc.)."""
    try:
        from PIL import Image

        Image.open(io.BytesIO(data)).verify()
        return True
    except Exception:
        return False


async def _fetch_portrait(
    client: httpx.AsyncClient, session: AsyncSession, seed: int
) -> tuple[bytes, str, str, str | None] | None:
    """Return (bytes, mime, license, credit/source_url) for one portrait, or None on failure."""
    pexels_key = await config_service.get(session, "bots.sources.pexels.api_key", "")
    if pexels_key:
        try:
            # Deterministic-ish page from the seed so personas don't all share one photo.
            page = (seed % 80) + 1
            resp = await client.get(
                _PEXELS_PORTRAIT,
                params={"query": "portrait person face", "per_page": 1, "page": page,
                        "orientation": "square"},
                headers={"Authorization": pexels_key},
                timeout=20.0,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos") or []
            if photos:
                src = photos[0]["src"].get("medium") or photos[0]["src"].get("original")
                img = await client.get(src, timeout=20.0, follow_redirects=True)
                img.raise_for_status()
                if _is_image(img.content):
                    credit = photos[0].get("photographer") or "Pexels"
                    return img.content, img.headers.get("content-type", "image/jpeg"), \
                        "Pexels License (free)", f"{credit} / Pexels"
        except Exception:
            log.warning("pexels portrait fetch failed (seed=%s); falling back", seed, exc_info=True)

    # Keyless fallback: a free portrait from randomuser.me (200 faces; free to use).
    gender = "women" if seed % 2 else "men"
    url = f"https://randomuser.me/api/portraits/{gender}/{seed % 100}.jpg"
    try:
        resp = await client.get(url, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
        if _is_image(resp.content):
            return resp.content, resp.headers.get("content-type", "image/jpeg"), \
                "Free for use (randomuser.me)", "randomuser.me"
    except Exception:
        log.warning("avatar fetch failed for seed=%s", seed, exc_info=True)
    return None


async def assign_avatar(
    client: httpx.AsyncClient, session: AsyncSession, user, seed: int
) -> str | None:
    """Download a portrait, store it (deduped by content hash), set ``user.avatar_url``.

    Returns the avatar URL, or None if no portrait could be fetched (caller commits).
    """
    fetched = await _fetch_portrait(client, session, seed)
    if fetched is None:
        return None
    data, mime, lic, credit = fetched
    digest = hashlib.sha256(data).hexdigest()[:64]

    # Dedup: reuse an identical portrait already stored (a few-hundred bots may share faces).
    twin = await session.scalar(select(Media).where(Media.content_hash == digest))
    if twin is not None and twin.storage_key:
        media = twin
    else:
        media = Media(
            kind="image", mime=mime, bytes=len(data), status="stored", disposition="pin",
            origin_kind="user", added_by=str(user.id), content_hash=digest,
            license=lic, credit=credit,
        )
        session.add(media)
        await session.flush()
        key = f"media/{media.id}"
        objectstore.put_bytes(key, data, content_type=mime)
        media.storage_key = key
        media.avail_state = "available"
        try:
            thumb_bytes, _ = make_thumbnail(data)
            thumb_key = f"media/{media.id}_thumb.jpg"
            objectstore.put_bytes(thumb_key, thumb_bytes, content_type="image/jpeg")
            media.thumbnail_key = thumb_key
        except Exception:
            log.warning("avatar thumbnail failed for %s", media.id, exc_info=True)

    # Match the URL shape the mobile web client builds for media (`/api/media/{id}/raw`).
    url = f"/api/media/{media.id}/raw"
    user.avatar_url = url
    return url
