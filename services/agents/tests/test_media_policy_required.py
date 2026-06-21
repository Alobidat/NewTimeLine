"""Pure tests for the no-text-only / clips-first media floor (ADR-0023)."""

from __future__ import annotations

from chronos_core.domain import media_policy as mp


def test_has_required_media_requires_an_image():
    # image is the floor; clips alone do not satisfy "no text-only" (hero must be showable).
    assert mp.has_required_media(1, 0) is True
    assert mp.has_required_media(2, 3) is True
    assert mp.has_required_media(0, 0) is False
    assert mp.has_required_media(0, 5) is False  # clips but no image → still a gap


def test_media_richness_classifies_none_image_clip():
    assert mp.media_richness(0, 0) == "none"
    assert mp.media_richness(2, 0) == "image"
    assert mp.media_richness(0, 1) == "clip"   # a clip wins even without an image…
    assert mp.media_richness(3, 1) == "clip"   # …and when both are present


def test_clip_kinds_is_video():
    assert "video" in mp.CLIP_KINDS
    assert "image" not in mp.CLIP_KINDS
