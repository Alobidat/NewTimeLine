"""Image thumbnail generation — produce a small JPEG preview from raw image bytes.

Used by the media-fetch worker after archiving an image to the object store: the thumbnail
is stored separately under ``media/{id}_thumb.jpg`` and served via ``/media/{id}/thumb``.
Non-image binaries (video, audio, embed) are skipped; the caller checks the MIME type first.
PIL is imported lazily so importing this module doesn't require Pillow at the API layer.
"""

from __future__ import annotations

import io

THUMB_SIZE = 320  # longest edge in pixels

_IMAGE_MIME_PREFIXES = ("image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp")


def is_image_mime(mime: str | None) -> bool:
    """Return True if *mime* identifies a raster image we can thumbnail."""
    if not mime:
        return False
    return any(mime.startswith(p) for p in _IMAGE_MIME_PREFIXES)


def make_thumbnail(data: bytes, *, size: int = THUMB_SIZE) -> tuple[bytes, str]:
    """Resize *data* so the longest edge ≤ *size*, preserving aspect ratio.

    Returns ``(jpeg_bytes, 'image/jpeg')``. Small images are not enlarged.
    Raises ``ValueError`` if the bytes cannot be decoded as a supported image.
    """
    from PIL import Image  # lazy — Pillow only required in the agents worker, not the API

    try:
        img = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"cannot decode image: {exc}") from exc

    img = img.convert("RGB")  # normalise: drop alpha/palette for uniform JPEG output
    img.thumbnail((size, size), Image.Resampling.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=80, optimize=True)
    return out.getvalue(), "image/jpeg"
