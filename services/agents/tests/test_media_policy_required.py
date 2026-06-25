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


# --- media quality: hero ranking + image quality floor (ADR-0024) ---


def test_media_role_rank_makes_the_first_clip_the_hero():
    # prefer_clips: a video at index 0 is the hero and outranks images.
    assert mp.media_role_rank("video", 0) == ("hero", 0)
    role, rank = mp.media_role_rank("image", 0)
    assert role == "gallery" and rank > 0          # image is NOT hero when a clip leads
    # a clip still ranks ahead of images even past the hero slot
    assert mp.media_role_rank("video", 1)[1] < mp.media_role_rank("image", 0)[1]


def test_media_role_rank_image_hero_when_clips_disabled():
    assert mp.media_role_rank("image", 0, prefer_clips=False) == ("hero", 0)
    assert mp.media_role_rank("video", 0, prefer_clips=False)[0] == "gallery"


def test_is_decent_image_rejects_known_tiny_widths_keeps_unknown():
    # The GALLERY floor: drop known icons, tolerate unknown (galleries don't need measurement).
    assert mp.is_decent_image(800) is True
    assert mp.is_decent_image(50, min_width=200) is False     # icon/placeholder
    assert mp.is_decent_image(None) is True                   # unknown → keep for gallery


def test_hero_eligible_requires_measured_image_at_or_above_floor():
    # The HERO floor (ADR-0024): an image must be MEASURED and >= 640; a clip is exempt.
    assert mp.hero_eligible("image", 640) is True
    assert mp.hero_eligible("image", 639) is False            # below the floor
    assert mp.hero_eligible("image", None) is False           # unmeasured → never hero (the leak)
    assert mp.hero_eligible("video", None) is True            # clip with unknown width is fine
    assert mp.hero_eligible("video", 120) is False            # known sub-floor clip is rejected
    assert mp.hero_eligible("video", 240) is True
