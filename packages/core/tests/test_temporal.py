"""Tests for the signed-year temporal axis (chronos_core.domain.temporal)."""

from datetime import datetime, timezone

import pytest

from chronos_core.domain.temporal import (
    TimePrecision,
    datetime_to_t,
    materialize_span,
    overlaps,
    precision_window,
    year_to_t,
)


def test_datetime_to_t_year_boundaries():
    assert datetime_to_t(datetime(2020, 1, 1, tzinfo=timezone.utc)) == pytest.approx(2020.0)
    assert datetime_to_t(datetime(2021, 1, 1, tzinfo=timezone.utc)) == pytest.approx(2021.0)


def test_datetime_to_t_midyear_leap():
    # 2020 is a leap year; 2 Jul is day 184 → ~half the year elapsed.
    t = datetime_to_t(datetime(2020, 7, 2, tzinfo=timezone.utc))
    assert t == pytest.approx(2020.5, abs=0.01)


def test_datetime_to_t_naive_is_utc():
    # Naive datetimes are treated as UTC (no crash, deterministic).
    assert datetime_to_t(datetime(1999, 1, 1)) == pytest.approx(1999.0)


def test_year_to_t():
    assert year_to_t(-1273) == -1273.0  # 1274 BC


@pytest.mark.parametrize(
    "t,precision,expected",
    [
        (1956.4, TimePrecision.YEAR, (1956.0, 1957.0)),
        (1956.0, TimePrecision.DECADE, (1950.0, 1960.0)),
        (1956.0, TimePrecision.CENTURY, (1900.0, 2000.0)),
        (-1273.2, TimePrecision.YEAR, (-1274.0, -1273.0)),  # BC floors correctly
    ],
)
def test_precision_window_grid(t, precision, expected):
    assert precision_window(t, precision) == pytest.approx(expected)


def test_precision_window_era_is_zero_width():
    assert precision_window(-4_000_000, TimePrecision.ERA) == (-4_000_000, -4_000_000)


def test_materialize_span_from_precision():
    assert materialize_span(1956.0, TimePrecision.YEAR) == pytest.approx((1956.0, 1957.0))


def test_materialize_span_explicit_end_wins():
    assert materialize_span(1900.0, TimePrecision.CENTURY, t_end=1945.0) == (1900.0, 1945.0)


def test_materialize_span_clamps_bad_end():
    # An end before the start is clamped up to the start (never negative-width).
    assert materialize_span(2000.0, TimePrecision.YEAR, t_end=1990.0) == (2000.0, 2000.0)


def test_materialize_span_deeptime_era():
    # Millions of years ago with an explicit span (the sub-timeline case).
    assert materialize_span(-4_000_000, TimePrecision.ERA, t_end=-3_500_000) == (
        -4_000_000,
        -3_500_000,
    )


@pytest.mark.parametrize(
    "span,window,expected",
    [
        ((1900.0, 2000.0), (1950.0, 1960.0), True),   # query inside span
        ((1956.0, 1957.0), (1900.0, 1956.5), True),   # partial overlap
        ((1956.0, 1957.0), (1958.0, 1959.0), False),  # disjoint after
        ((1956.0, 1957.0), (1940.0, 1955.0), False),  # disjoint before
        ((1956.0, 1957.0), (1957.0, 1958.0), True),   # touching boundary
    ],
)
def test_overlaps(span, window, expected):
    assert overlaps(span[0], span[1], window[0], window[1]) is expected
