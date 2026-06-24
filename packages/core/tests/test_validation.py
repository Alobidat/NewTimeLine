"""Unit tests for the source-validation math (chronos_core.domain.validation)."""

from __future__ import annotations

from chronos_core.domain import validation


def test_vote_weight_rises_sublinearly_with_reputation():
    assert validation.vote_weight(0) == 1.0
    assert validation.vote_weight(10) > validation.vote_weight(0)
    # Sub-linear: 100x the rep is far less than 100x the weight.
    assert validation.vote_weight(100) < 10 * validation.vote_weight(1)


def test_source_quality_neutral_without_votes():
    assert validation.source_quality(0, 0, 0) == 50


def test_source_quality_rises_with_corroboration_falls_with_dispute():
    up = validation.source_quality(corroborate_w=10, dispute_w=0, irrelevant_w=0)
    down = validation.source_quality(corroborate_w=0, dispute_w=10, irrelevant_w=0)
    assert up > 50 > down
    assert 0 <= down < up <= 100


def test_source_quality_damped_for_tiny_samples():
    # A single corroborate nudges above 50 but doesn't slam to 100.
    one = validation.source_quality(1, 0, 0)
    many = validation.source_quality(50, 0, 0)
    assert 50 < one < many <= 100


def test_blended_confidence_blends_count_and_quality():
    # High-quality sources lift confidence above the bare source-count baseline.
    low_q = validation.blended_confidence(3, avg_source_quality=20,
                                          event_corroborate_w=0, event_dispute_w=0)
    high_q = validation.blended_confidence(3, avg_source_quality=90,
                                           event_corroborate_w=0, event_dispute_w=0)
    assert high_q > low_q
    # A net-dispute verdict on the event drags confidence down vs net-corroborate.
    corr = validation.blended_confidence(3, 60, event_corroborate_w=10, event_dispute_w=0)
    disp = validation.blended_confidence(3, 60, event_corroborate_w=0, event_dispute_w=10)
    assert corr > disp
    assert all(0 <= v <= 100 for v in (low_q, high_q, corr, disp))
