"""Unit tests for the thumbnail helper — pure image logic, no DB needed."""

from __future__ import annotations

import io

import pytest

from chronos_core.domain.thumbnails import is_image_mime, make_thumbnail


def _png(width: int, height: int) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _open(data: bytes):
    from PIL import Image

    return Image.open(io.BytesIO(data))


def test_is_image_mime_true():
    for mime in ("image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"):
        assert is_image_mime(mime), mime


def test_is_image_mime_false():
    assert not is_image_mime("video/mp4")
    assert not is_image_mime("audio/mpeg")
    assert not is_image_mime("application/octet-stream")
    assert not is_image_mime(None)
    assert not is_image_mime("")


def test_thumbnail_shrinks_large_image():
    thumb_bytes, mime = make_thumbnail(_png(1200, 800), size=320)
    assert mime == "image/jpeg"
    img = _open(thumb_bytes)
    assert img.width <= 320
    assert img.height <= 320


def test_thumbnail_preserves_aspect_ratio():
    thumb_bytes, _ = make_thumbnail(_png(800, 400), size=320)  # 2:1
    img = _open(thumb_bytes)
    assert img.width == 320
    assert img.height == 160


def test_thumbnail_does_not_enlarge_small_image():
    thumb_bytes, _ = make_thumbnail(_png(100, 80), size=320)
    img = _open(thumb_bytes)
    assert img.width == 100
    assert img.height == 80


def test_thumbnail_square_fits_within_size():
    thumb_bytes, _ = make_thumbnail(_png(500, 500), size=320)
    img = _open(thumb_bytes)
    assert img.width == 320
    assert img.height == 320


def test_thumbnail_raises_on_non_image():
    with pytest.raises(ValueError, match="cannot decode"):
        make_thumbnail(b"this is not image data at all")
