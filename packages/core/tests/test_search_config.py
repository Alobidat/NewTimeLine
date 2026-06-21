"""Tests for the faceted-search config keys + the SearchResults DTO (ADR-0022 / §5)."""

from __future__ import annotations

import uuid

from chronos_core.config_service import DEFAULTS
from chronos_core.config_spec import SPEC_BY_KEY, validate_value
from chronos_core.schemas.graph import EntityRead, SearchResults

_SEARCH_KEYS = [
    "search.live_collection.enabled",
    "search.facet_limit",
    "search.stream.poll_seconds",
    "search.stream.max_seconds",
]


def test_search_keys_have_specs_and_are_seeded():
    for key in _SEARCH_KEYS:
        assert key in SPEC_BY_KEY, key
        assert key in DEFAULTS, key
        # API-owned (no component manifest), scoped under "search".
        assert SPEC_BY_KEY[key].component_id is None
        assert SPEC_BY_KEY[key].scope == "search"


def test_search_keys_validate():
    assert validate_value("search.live_collection.enabled", True) == (True, None)
    assert validate_value("search.live_collection.enabled", "yes")[0] is False
    assert validate_value("search.facet_limit", 10) == (True, None)
    assert validate_value("search.facet_limit", 0)[0] is False
    assert validate_value("search.facet_limit", 999)[0] is False
    assert validate_value("search.stream.poll_seconds", 3) == (True, None)
    assert validate_value("search.stream.max_seconds", 120) == (True, None)


def _entity(kind: str, name: str) -> EntityRead:
    return EntityRead(id=uuid.uuid4(), kind=kind, name=name)


def test_search_results_dto_defaults_and_facets():
    r = SearchResults(subject="strike Iran")
    assert r.collecting is False
    assert r.events == [] and r.actors == [] and r.places == []

    r2 = SearchResults(
        subject="Iran",
        collecting=True,
        actors=[_entity("person", "Khomeini")],
        places=[_entity("place", "Tehran")],
    )
    dumped = r2.model_dump()
    assert dumped["subject"] == "Iran"
    assert dumped["collecting"] is True
    assert dumped["actors"][0]["name"] == "Khomeini"
    assert dumped["places"][0]["kind"] == "place"
