"""Pure-logic tests for the media archival decision engine (ADR-0018)."""

from __future__ import annotations

from chronos_core.domain import media_policy as mp


def test_sensitivity_from_category_tags_and_social_origin():
    assert mp.score_sensitivity("news", []) == 0
    assert mp.score_sensitivity("conflict", []) == 40
    # category + two sensitive tags + social origin
    s = mp.score_sensitivity("conflict", ["war", "killed"], source_kind="social")
    assert s == 40 + 30 + 20
    assert mp.score_sensitivity("politics", ["a", "b", "c", "d"]) <= 100


def test_origin_ephemerality_classification():
    assert mp.origin_ephemerality("social", None) == "ephemeral"
    assert mp.origin_ephemerality(None, "twitter.com") == "ephemeral"
    assert mp.origin_ephemerality(None, "mobile.twitter.com") == "ephemeral"  # subdomain
    assert mp.origin_ephemerality("encyclopedia", None) == "durable"
    assert mp.origin_ephemerality(None, "commons.wikimedia.org") == "durable"
    assert mp.origin_ephemerality("news", "example.com") == "mixed"


def test_high_sensitivity_always_pins():
    assert mp.decide_disposition(80, "durable", stable_sources=5) == "pin"


def test_durable_low_sensitivity_corroborated_links():
    assert mp.decide_disposition(10, "durable", stable_sources=1) == "link"


def test_ephemeral_archives():
    assert mp.decide_disposition(10, "ephemeral") == "archive"


def test_ambiguous_defaults_to_archive_first():
    assert mp.decide_disposition(10, "mixed") == "archive"
    assert mp.decide_disposition(10, "mixed", default_archive=False) == "link"


def test_persistence_confidence_grows_with_sources_and_time():
    assert mp.persistence_confidence(0, 0) == 0
    low = mp.persistence_confidence(1, 5)
    high = mp.persistence_confidence(3, 90)
    assert low < high <= 100


def test_should_release_only_durable_nonsensitive_archives():
    # pinned / sensitive never released
    assert mp.should_release("pin", 10, 100) is False
    assert mp.should_release("archive", 90, 100) is False
    assert mp.should_release("archive", 10, 100, pinned=True) is False
    # durable, non-sensitive archive above threshold → release
    assert mp.should_release("archive", 10, 80, threshold=70) is True
    assert mp.should_release("archive", 10, 50, threshold=70) is False
