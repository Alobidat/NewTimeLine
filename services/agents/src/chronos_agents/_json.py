"""Tolerant JSON extraction from LLM responses (shared by the enricher + bot engines).

Local models often wrap their JSON in prose or ``` fences; these helpers pull the first JSON
*object* or *array* out of a response without choking on the surrounding noise.
"""

from __future__ import annotations

import json
from typing import Any


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
    return text


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response. Raises ValueError if none."""
    text = _strip_fences(text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])


def extract_json_array(text: str) -> list[Any]:
    """Pull the first JSON array out of a model response. Raises ValueError if none."""
    text = _strip_fences(text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON array in response")
    out = json.loads(text[start : end + 1])
    if not isinstance(out, list):
        raise ValueError("parsed value is not a list")
    return out
