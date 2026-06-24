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
    """Pull the first JSON array out of a model response. Raises ValueError if none.

    Tolerant of a malformed element deep in a long array (local models sometimes emit one):
    rather than lose the whole batch, fall back to decoding element-by-element and keep the
    well-formed leading run.
    """
    text = _strip_fences(text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON array in response")
    body = text[start : end + 1]
    try:
        out = json.loads(body)
    except json.JSONDecodeError:
        out = _salvage_array(body)
    if not isinstance(out, list):
        raise ValueError("parsed value is not a list")
    return out


def _salvage_array(body: str) -> list[Any]:
    """Best-effort recovery of the consecutive well-formed elements of a malformed JSON array.

    Decodes one element at a time from just after the opening ``[``, stopping at the first
    element that won't parse. Returns whatever valid prefix was recovered (possibly empty).
    """
    decoder = json.JSONDecoder()
    items: list[Any] = []
    i = body.find("[") + 1
    n = len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n,":  # skip whitespace + element separators
            i += 1
        if i >= n or body[i] == "]":
            break
        try:
            obj, i = decoder.raw_decode(body, i)
        except json.JSONDecodeError:
            break
        items.append(obj)
    return items
