"""Tests for severity scoring (chronos_core.domain.severity)."""

import pytest

from chronos_core.domain.severity import (
    SeverityWeights,
    compute_severity,
    normalize_corroboration,
)


def test_weights_defaults_sum_to_one():
    w = SeverityWeights()
    assert w.impact + w.social + w.corroboration == pytest.approx(1.0)


def test_weights_from_config_partial_override():
    w = SeverityWeights.from_config({"impact": 0.7})
    assert w.impact == 0.7
    assert w.social == SeverityWeights().social  # untouched default


def test_normalize_corroboration_monotonic_and_bounded():
    assert normalize_corroboration(0) == 0.0
    a, b, c = (normalize_corroboration(n) for n in (1, 4, 100))
    assert 0 < a < b < c < 1  # increasing, saturating below 1
    assert normalize_corroboration(4, half=4.0) == pytest.approx(0.5)


def test_compute_severity_corroboration_only_is_deterministic():
    # 4 sources at half=4 → corroboration 0.5; default weight 0.3 → score 15.
    r = compute_severity(source_count=4)
    assert r.corroboration == pytest.approx(0.5)
    assert r.score == 15
    assert r.impact == 0.0 and r.social == 0.0


def test_compute_severity_bounds():
    r = compute_severity(source_count=10_000, engagement=1e9, impact_raw=1e9)
    assert 0 <= r.score <= 100
    assert r.score > 80  # everything maxed → high


def test_compute_severity_empty_is_zero():
    assert compute_severity().score == 0
