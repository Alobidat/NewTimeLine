"""Pure-logic tests for entity name normalization + relation-weight scoring."""

from __future__ import annotations

from chronos_core.domain.entities import entity_name_key, relation_weight


def test_name_key_normalizes_case_and_whitespace():
    assert entity_name_key("  United   STATES ") == "united states"
    assert entity_name_key("Iran") == "iran"
    # Equal mentions collapse to one resolution key.
    assert entity_name_key("United States") == entity_name_key("united states")


def test_relation_weight_zero_when_nothing_shared():
    assert relation_weight(0) == 0.0


def test_relation_weight_grows_with_shared_entities_and_saturates():
    w1 = relation_weight(1)
    w2 = relation_weight(2)
    w3 = relation_weight(3)
    assert 0 < w1 < w2 < w3 < 1.0


def test_shared_location_boosts_weight():
    plain = relation_weight(1)
    located = relation_weight(1, shares_location=True)
    assert located > plain
    assert located <= 1.0
