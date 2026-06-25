"""Shared image measurement (Pillow) — read a remote image's real pixel dimensions.

Used at publish time (``publish.attach_media``) so an unmeasured image can be quality-gated
before it becomes a hero, and by the media-quality guard to measure the corpus. Bounded +
best-effort: a fetch/decode failure or oversized body returns ``None`` rather than raising.
"""

from __future__ import annotations

import io
import logging

import httpx
from PIL import Image

log = logging.getLogger("chronos.agents.media_measure")

MAX_IMAGE_BYTES = 12 * 1024 * 1024  # never pull more than this just to measure an image


async def measure_image(
    client: httpx.AsyncClient, url: str, *, max_bytes: int = MAX_IMAGE_BYTES
) -> tuple[int, int] | None:
    """Return ``(width, height)`` for the image at ``url``, or ``None`` if it can't be read."""
    if not url:
        return None
    try:
        resp = await client.get(url, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
        data = resp.content
        if len(data) > max_bytes:
            return None
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
        return (int(w), int(h)) if w and h else None
    except Exception:  # noqa: BLE001 - measurement is best-effort; never break the caller
        return None
