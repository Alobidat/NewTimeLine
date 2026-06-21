"""Unit tests for the Embedder client and dedup domain helpers."""

from __future__ import annotations

import pytest
import httpx
import respx

from chronos_core.llm.embedder import Embedder


@respx.mock
async def test_embedder_returns_ordered_vectors():
    """Embedder should sort by .index so vectors match input order."""
    route = respx.post("http://localhost:11434/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2, 0.3]},
                    {"index": 0, "embedding": [0.1, 0.9]},
                ]
            },
        )
    )
    embedder = Embedder("http://localhost:11434/v1", "test-model")
    result = await embedder.embed(["text a", "text b"])
    await embedder.aclose()

    assert route.called
    assert result[0] == [0.1, 0.9]   # index 0 → first input
    assert result[1] == [0.2, 0.3]   # index 1 → second input


@respx.mock
async def test_embedder_empty_input():
    embedder = Embedder("http://localhost:11434/v1", "test-model")
    result = await embedder.embed([])
    await embedder.aclose()
    assert result == []


@respx.mock
async def test_embedder_sends_auth_header():
    route = respx.post("http://api.example.com/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.5, 0.5]}]},
        )
    )
    embedder = Embedder("http://api.example.com/v1", "embed-model", api_key="sk-test")
    await embedder.embed(["hello"])
    await embedder.aclose()

    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test"
