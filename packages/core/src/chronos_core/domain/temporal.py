"""Temporal model helpers — the signed-year time axis (ADR-0012).

The canonical time of every event/subject is a signed numeric *year* (``t``), so the
timeline spans all of history uniformly: ``2011.19`` (≈Mar 2011), ``-1273`` (1274 BC),
``-4_000_000`` (≈4 Mya). This module is pure (stdlib only) so it is cheap to test and
reuse across services. See docs/data-model.md §1.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime
from enum import StrEnum

# Width (in years) of each precision's window. 'exact'/'day' are sub-year; we treat them
# as a single day for span purposes. 'era' has no fixed width — callers must supply t_end.
_PRECISION_YEARS: dict[str, float] = {
    "exact": 1.0 / 365.25,
    "day": 1.0 / 365.25,
    "month": 1.0 / 12.0,
    "year": 1.0,
    "decade": 10.0,
    "century": 100.0,
}


class TimePrecision(StrEnum):
    """How precisely an anchor time is known. Drives rendering + t_end derivation."""

    EXACT = "exact"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    DECADE = "decade"
    CENTURY = "century"
    ERA = "era"


def datetime_to_t(dt: datetime) -> float:
    """Convert a (modern) datetime to a fractional signed year.

    Used when ingesting source publication dates. The fraction is the position within the
    year, accurate enough for timeline plotting (exact instants are kept separately in the
    ``instant`` column).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    year_days = 366.0 if calendar.isleap(dt.year) else 365.0
    start = datetime(dt.year, 1, 1, tzinfo=UTC)
    elapsed = (dt - start).total_seconds()
    return dt.year + elapsed / (year_days * 86400.0)


def year_to_t(year: int) -> float:
    """Convert an integer (astronomical) year to ``t``. Year 0 = 1 BC, -1 = 2 BC, etc."""
    return float(year)


def precision_window(t: float, precision: TimePrecision | str) -> tuple[float, float]:
    """Return the ``[start, end)`` span (in years) that a precision implies for anchor ``t``.

    The anchor is floored to the precision grid so e.g. precision ``century`` at ``t=1956``
    yields ``[1900, 2000)``. ``era`` has no implied width — callers must pass an explicit
    end (we return a zero-width window here as a safe default).
    """
    p = TimePrecision(precision)
    if p is TimePrecision.ERA:
        return (t, t)

    width = _PRECISION_YEARS[p.value]
    if p in (TimePrecision.EXACT, TimePrecision.DAY, TimePrecision.MONTH):
        # Sub-/intra-year: keep the anchor as-is, add the small width.
        return (t, t + width)

    # year / decade / century: floor the anchor onto the grid.
    grid = width
    import math

    start = math.floor(t / grid) * grid
    return (start, start + grid)


def materialize_span(
    t_start: float,
    precision: TimePrecision | str,
    t_end: float | None = None,
) -> tuple[float, float]:
    """Compute the stored ``(t_start, t_end)`` for an event/subject.

    ``t_end`` is materialized at write time so timeline-overlap queries are a plain indexable
    range test (see docs/data-model.md §1.1). If an explicit end is given it wins (clamped to
    be >= start); otherwise the precision window's end is used.
    """
    if t_end is not None:
        return (t_start, max(t_start, t_end))
    _, end = precision_window(t_start, precision)
    return (t_start, max(t_start, end))


def overlaps(t_start: float, t_end: float, q0: float, q1: float) -> bool:
    """True if span ``[t_start, t_end]`` overlaps query window ``[q0, q1]``."""
    return t_start <= q1 and t_end >= q0
