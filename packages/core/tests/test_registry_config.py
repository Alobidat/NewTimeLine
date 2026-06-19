"""Tests for the component registry + config specs that drive the Admin Portal."""

from __future__ import annotations

from chronos_core import registry
from chronos_core.config_service import DEFAULTS
from chronos_core.config_spec import SPEC_BY_KEY, SPECS, validate_value
from chronos_core.registry import ACTIONS


def test_component_ids_unique_and_actions_known():
    ids = [m.id for m in registry.REGISTRY]
    assert len(ids) == len(set(ids))
    for m in registry.REGISTRY:
        assert all(a in ACTIONS for a in m.actions)


def test_enabled_key_and_config_prefix_have_specs():
    for m in registry.REGISTRY:
        if m.enabled_key:
            assert m.enabled_key in SPEC_BY_KEY, m.enabled_key
        if m.config_prefix:
            owned = [s for s in SPECS if s.key.startswith(m.config_prefix)]
            assert owned, f"no config specs for {m.id} ({m.config_prefix})"


def test_spec_component_ids_resolve():
    valid = {m.id for m in registry.REGISTRY} | {None}
    for s in SPECS:
        assert s.component_id in valid, s.key


def test_defaults_derived_from_specs():
    # Single source of truth: config_service.DEFAULTS == specs' (default, scope).
    assert DEFAULTS == {s.key: (s.default, s.scope) for s in SPECS}


def test_validate_value_types_and_ranges():
    assert validate_value("agents.enrich.enabled", True) == (True, None)
    assert validate_value("agents.enrich.enabled", "yes")[0] is False
    assert validate_value("agents.enrich.batch_size", 10) == (True, None)
    assert validate_value("agents.enrich.batch_size", 0)[0] is False        # below minimum
    assert validate_value("agents.enrich.batch_size", 9999)[0] is False     # above maximum
    assert validate_value("agents.enrich.batch_size", 1.5)[0] is False      # not integer
    assert validate_value("llm.routing", {"primary": "ollama"}) == (True, None)
    assert validate_value("llm.routing", "nope")[0] is False
    assert validate_value("nonexistent.key", 1)[0] is False
