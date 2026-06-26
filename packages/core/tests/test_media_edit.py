"""Unit tests for the Creator-Studio edit-spec normalizer (pure, no I/O)."""

from __future__ import annotations

from chronos_core.domain.media_edit import MAX_SPEED, MIN_SPEED, normalize_edit_spec


def test_none_when_no_edits():
    assert normalize_edit_spec() is None
    assert normalize_edit_spec(trim_start=0, trim_end=0, speed=1.0) is None


def test_trim_window_kept_and_rounded():
    # sub-millisecond precision is dropped (rounded to 3 dp).
    assert normalize_edit_spec(trim_start=1.500777, trim_end=9.0) == {
        "trim_start": 1.501, "trim_end": 9.0,
    }


def test_trim_end_alone_is_valid():
    assert normalize_edit_spec(trim_end=8.0) == {"trim_end": 8.0}


def test_invalid_window_drops_trim_keeps_speed():
    # end <= start is not a usable window: drop the trim, keep a valid speed.
    out = normalize_edit_spec(trim_start=5.0, trim_end=5.0, speed=2.0)
    assert out == {"speed": 2.0}
    assert normalize_edit_spec(trim_start=9.0, trim_end=3.0) is None


def test_speed_clamped_to_range():
    assert normalize_edit_spec(speed=10.0) == {"speed": MAX_SPEED}
    assert normalize_edit_spec(speed=0.01) == {"speed": MIN_SPEED}
    assert normalize_edit_spec(speed=1.0) is None  # a no-op speed is dropped


def test_garbage_inputs_ignored():
    assert normalize_edit_spec(trim_start="abc", trim_end=None, speed="x") is None
    assert normalize_edit_spec(speed=True) is None  # bools are not speeds
    assert normalize_edit_spec(trim_start=float("nan")) is None
    assert normalize_edit_spec(trim_start=float("inf")) is None


def test_numeric_strings_accepted():
    assert normalize_edit_spec(trim_start="1.5", trim_end="4", speed="2") == {
        "trim_start": 1.5, "trim_end": 4.0, "speed": 2.0,
    }
