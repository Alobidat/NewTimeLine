"""Tests for the pure normalizers (chronos_agents.normalize)."""

from datetime import datetime, timezone

import pytest

from chronos_agents.normalize import (
    normalize_rss,
    normalize_wikidata,
    parse_point_wkt,
    parse_wikidata_time,
    wikidata_time_to_t,
)
from chronos_core.domain.temporal import TimePrecision


def test_parse_point_wkt():
    p = parse_point_wkt("Point(-0.1257 51.5085)")
    assert p is not None and p.lon == pytest.approx(-0.1257) and p.lat == pytest.approx(51.5085)


def test_parse_point_wkt_bad():
    assert parse_point_wkt(None) is None
    assert parse_point_wkt("not wkt") is None


def test_parse_wikidata_time_modern():
    assert parse_wikidata_time("2011-03-11T00:00:00Z") == (2011, 3, 11)


def test_parse_wikidata_time_bc():
    # 44 BC (assassination of Caesar) — negative year, must not go through datetime.
    assert parse_wikidata_time("-0044-03-15T00:00:00Z") == (-44, 3, 15)


def test_parse_wikidata_time_coarse_month_day_zero():
    # Wikidata uses 00 for unknown month/day; we clamp to 1.
    assert parse_wikidata_time("1066-00-00T00:00:00Z") == (1066, 1, 1)


def test_wikidata_time_to_t_is_signed_and_ordered():
    assert wikidata_time_to_t(-44, 3, 15) < 0
    assert wikidata_time_to_t(2011, 1, 1) < wikidata_time_to_t(2011, 12, 1)


def test_normalize_rss_happy():
    cand = normalize_rss(
        {
            "title": "Quake hits region",
            "link": "https://news.example/a",
            "summary": "A summary",
            "published": datetime(2026, 1, 2, tzinfo=timezone.utc),
        },
        feed_publisher="Example News",
    )
    assert cand is not None
    assert cand.time_precision is TimePrecision.DAY
    assert cand.source_url == "https://news.example/a"
    assert cand.t_start == pytest.approx(2026.0, abs=0.02)


def test_normalize_rss_requires_date_and_link():
    assert normalize_rss({"title": "x", "link": "y", "published": None}) is None
    assert normalize_rss({"title": "x", "published": datetime(2020, 1, 1)}) is None


def test_normalize_wikidata_bc_with_coords():
    cand = normalize_wikidata(
        {
            "label": "Battle of Example",
            "time": "-0044-03-15T00:00:00Z",
            "coord": "Point(12.5 41.9)",
            "article": "https://en.wikipedia.org/wiki/Example",
        }
    )
    assert cand is not None
    assert cand.t_start < 0  # BC
    assert cand.geo is not None and cand.geo.lat == pytest.approx(41.9)
    assert cand.source_publisher == "Wikipedia"
