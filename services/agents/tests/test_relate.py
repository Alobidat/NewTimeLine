"""Tests for the relation-linker's pure edge-kind logic."""

from __future__ import annotations

from chronos_agents.relate import _edge_kinds


def test_shared_place_only_is_same_place_not_causal():
    assert _edge_kinds(shares_place=True, shares_actor=False, shared=1) == ["same-place"]


def test_shared_actor_only_is_same_actor_not_causal():
    assert _edge_kinds(shares_place=False, shares_actor=True, shared=1) == ["same-actor"]


def test_place_and_actor_implies_precursor_chain():
    kinds = _edge_kinds(shares_place=True, shares_actor=True, shared=2)
    assert kinds == ["same-place", "same-actor", "precursor"]


def test_two_shared_entities_implies_precursor_even_without_both_flags():
    # e.g. two shared topics → still a candidate causal chain.
    assert "precursor" in _edge_kinds(shares_place=False, shares_actor=False, shared=2)


def test_single_weak_overlap_is_not_a_chain():
    assert _edge_kinds(shares_place=False, shares_actor=False, shared=1) == []
