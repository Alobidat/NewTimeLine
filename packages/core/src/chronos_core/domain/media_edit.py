"""Creator-Studio clip edit spec (pure, no I/O) — validate/normalize the trim+speed the
transcode agent applies when building a clip's ``web`` variant (Phase 1).

The editor (or any client) sends a trim window and/or a speed multiplier; this turns that raw,
possibly-malformed input into a minimal, sane ``edit_spec`` dict (or ``None`` when there's
nothing to do). Single source of truth so the upload router and the transcode agent agree on
what a valid edit is. Kept pure + dependency-free so it's trivially unit-tested.

Shape: ``{"trim_start": float, "trim_end": float, "speed": float}`` — every key optional.
"""

from __future__ import annotations

# ffmpeg's atempo filter handles 0.5–2.0 in one pass; we keep speed in that range for Phase 1
# (chaining for more extreme speeds can come later) so a single ``atempo`` always suffices.
MIN_SPEED = 0.5
MAX_SPEED = 2.0


def _clean_float(value: object) -> float | None:
    """Coerce a form/JSON value to a float, or ``None`` if it isn't a finite number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)  # accepts int / float / numeric str
    except (TypeError, ValueError):
        return None
    # reject NaN / ±inf (NaN != NaN)
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def normalize_edit_spec(
    *, trim_start: object = None, trim_end: object = None, speed: object = None
) -> dict | None:
    """Build a clean ``edit_spec`` from raw inputs, dropping anything that's a no-op or invalid.

    Rules: a positive ``trim_start``/``trim_end`` is kept (rounded to ms); a trim window whose
    end isn't after its start is discarded (the trim, not the whole spec); ``speed`` is clamped
    to ``[MIN_SPEED, MAX_SPEED]`` and dropped when it lands back on 1.0. Returns ``None`` when no
    meaningful edit remains, so callers store NULL and the agent skips the edit path entirely.
    """
    spec: dict[str, float] = {}

    ts = _clean_float(trim_start)
    te = _clean_float(trim_end)
    if ts is not None and ts > 0:
        spec["trim_start"] = round(ts, 3)
    if te is not None and te > 0:
        spec["trim_end"] = round(te, 3)
    # An end that isn't strictly after the start is not a usable window — drop just the trim.
    if "trim_end" in spec and spec["trim_end"] <= spec.get("trim_start", 0.0):
        spec.pop("trim_start", None)
        spec.pop("trim_end", None)

    sp = _clean_float(speed)
    if sp is not None and sp > 0:
        sp = round(max(MIN_SPEED, min(MAX_SPEED, sp)), 3)
        if sp != 1.0:
            spec["speed"] = sp

    return spec or None
