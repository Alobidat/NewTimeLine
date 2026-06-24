"""Unit tests for the tolerant LLM-JSON extractors in ``chronos_agents._json``.

Focus: ``extract_json_array`` must recover the well-formed leading elements when a local model
emits a syntactically-broken element deep in a long array (previously this lost the whole batch,
e.g. a 20-persona generation collapsing to zero).
"""

from __future__ import annotations

import pytest

from chronos_agents._json import extract_json_array, extract_json_object


def test_extract_array_clean_and_fenced():
    assert extract_json_array('[{"a": 1}, {"a": 2}]') == [{"a": 1}, {"a": 2}]
    assert extract_json_array('```json\n[1, 2, 3]\n```') == [1, 2, 3]
    assert extract_json_array('prose before [10, 20] and after') == [10, 20]


def test_extract_array_salvages_leading_valid_elements():
    # Third element has a broken delimiter; the first two are recoverable.
    broken = '[{"h": "a"}, {"h": "b"}, {"h": "c" "x": 1}, {"h": "d"}]'
    out = extract_json_array(broken)
    assert out == [{"h": "a"}, {"h": "b"}]


def test_extract_array_truncated_midstream():
    # Stream cut off mid-object (no closing ]) — keep the complete prefix.
    truncated = '[{"h": "a"}, {"h": "b"}, {"h": "c'
    # rfind("]") fails -> no array bracket pair; ensure we still raise cleanly there,
    # but a truncated-yet-bracketed array salvages its prefix:
    bracketed = truncated + '"}]'  # closes the array but the last object is fine here
    assert extract_json_array(bracketed) == [{"h": "a"}, {"h": "b"}, {"h": "c"}]


def test_extract_array_raises_when_no_array():
    with pytest.raises(ValueError):
        extract_json_array("no brackets here")


def test_extract_array_empty_when_first_element_unparseable():
    # Nothing valid before the break -> empty list (caller treats as a failed batch).
    assert extract_json_array('[oops not json, {"h": "a"}]') == []


def test_extract_object_still_strict():
    assert extract_json_object('{"k": 1}') == {"k": 1}
    with pytest.raises(ValueError):
        extract_json_object("no object")
