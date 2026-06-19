"""Tests for the relation-linker's pure edge-kind logic."""

from __future__ import annotations

from chronos_agents.relate import _edge_kinds


def test_shared_place_is_same_place():
    assert _edge_kinds(shares_place=True, shares_actor=False) == ["same-place"]


def test_shared_actor_is_same_actor():
    assert _edge_kinds(shares_place=False, shares_actor=True) == ["same-actor"]


def test_place_and_actor_gives_both_cooccurrence_kinds():
    assert _edge_kinds(shares_place=True, shares_actor=True) == ["same-place", "same-actor"]


def test_never_infers_causal_or_precursor():
    # Co-occurrence only — the causal chain comes from curated/LLM links, not shared entities.
    for kinds in (
        _edge_kinds(shares_place=True, shares_actor=True),
        _edge_kinds(shares_place=True, shares_actor=False),
        _edge_kinds(shares_place=False, shares_actor=True),
    ):
        assert "precursor" not in kinds and "causal" not in kinds


def test_no_overlap_is_no_edge():
    assert _edge_kinds(shares_place=False, shares_actor=False) == []
