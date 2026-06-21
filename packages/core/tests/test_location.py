"""Unit tests for the pure location-resolution helpers (ADR-0020 cascade steps 4 & 5).

No DB, no network — these cover the curated tables: text extraction, centroids, and the
news-agency → country mapping.
"""

from __future__ import annotations

from chronos_core.domain import location


def test_centroid_known_and_unknown():
    assert location.centroid("Iran") is not None
    lat, lon = location.centroid("Iran")
    assert 25 < lat < 40 and 44 < lon < 64
    assert location.centroid("Atlantis") is None


def test_extract_countries_by_name():
    got = location.extract_countries("Tensions rise between the United States and Iran")
    assert got == ["United States", "Iran"]


def test_extract_countries_by_demonym_and_capital():
    got = location.extract_countries("Iranian officials met counterparts in Washington")
    assert "Iran" in got
    assert "United States" in got


def test_extract_countries_first_seen_order_and_dedup():
    got = location.extract_countries(
        "Iran and the US clashed; later the US responded and Iran replied"
    )
    assert got == ["Iran", "United States"]


def test_extract_countries_scans_multiple_texts():
    got = location.extract_countries("A French statement", None, "issued from Berlin")
    assert got == ["France", "Germany"]


def test_extract_countries_empty_and_none():
    assert location.extract_countries() == []
    assert location.extract_countries(None, "") == []
    assert location.extract_countries("no places named here") == []


def test_extract_countries_word_boundary():
    # 'us' must not match inside 'business'; 'America' (alias) is the real hit.
    got = location.extract_countries("the business news from America")
    assert got == ["United States"]


def test_domain_country_exact_and_subdomain():
    assert location.domain_country("bbc.co.uk") == "United Kingdom"
    assert location.domain_country("www.cnn.com") == "United States"
    assert location.domain_country("edition.cnn.com") == "United States"
    assert location.domain_country("presstv.ir") == "Iran"


def test_domain_country_unknown_and_none():
    assert location.domain_country("example.com") is None
    assert location.domain_country(None) is None
    assert location.domain_country("") is None


def test_every_alias_resolves_to_a_known_centroid():
    # Guard: an alias pointing at a country with no centroid would silently never extract.
    for canonical in location._ALIASES.values():
        assert canonical in location.COUNTRY_CENTROIDS, canonical
