"""Integrity tests for the curated US–Iran PoC dataset (pure; no DB)."""

from __future__ import annotations

from chronos_core.domain import media_policy as mp

from chronos_agents.seed_iran_us import EVENTS, RELATIONS


def test_every_relation_references_known_events():
    keys = {e.key for e in EVENTS}
    for src, dst, _kind in RELATIONS:
        assert src in keys and dst in keys, (src, dst)


def test_relation_kinds_are_chain_kinds():
    assert {k for _s, _d, k in RELATIONS} <= {"causal", "precursor", "sequel"}


def test_us_and_iran_tagged_on_every_event_for_intersection():
    # The "all events linking the US and Iran" query relies on both being tagged.
    for ev in EVENTS:
        names = {e.name for e in ev.entities}
        assert "United States" in names and "Iran" in names, ev.key


def test_every_event_has_a_source():
    for ev in EVENTS:
        assert ev.sources, ev.key


def test_media_covers_the_archival_spectrum():
    # Each event's lead image (origin = ev.image_origin) should span link/archive/pin (ADR-0018).
    dispositions = set()
    for ev in EVENTS:
        sensitivity = mp.score_sensitivity(ev.category, ev.tags, source_kind=ev.image_origin)
        ephem = mp.origin_ephemerality(ev.image_origin, None)
        stable = 1 if ephem == "durable" else 0
        dispositions.add(mp.decide_disposition(sensitivity, ephem, stable_sources=stable))
    assert {"link", "archive", "pin"} <= dispositions, dispositions


def test_soleimani_anchor_has_back_and_forward_edges():
    # The PoC anchor must be diggable both directions.
    back = [s for s, d, _ in RELATIONS if d == "soleimani2020"]
    forward = [d for s, d, _ in RELATIONS if s == "soleimani2020"]
    assert back and forward
