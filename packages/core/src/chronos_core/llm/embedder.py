"""Lightweight embedding client for OpenAI-compatible /embeddings endpoints.

Used by the Deduper (Phase 3b) to fill ``events.embedding`` via any local or cloud
embedding model (Ollama ``mxbai-embed-large``, OpenAI ``text-embedding-3-*``, etc.).
The dimension MUST match ``EMBEDDING_DIM`` in ``chronos_core.models.event`` (default 1024).
"""

from __future__ import annotations

import logging
import os

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core import config_service

log = logging.getLogger("chronos.llm.embedder")

_DEFAULT_BASE_URL = "http://host.docker.internal:11434/v1"
_DEFAULT_MODEL = "mxbai-embed-large"


class Embedder:
    """Calls POST {base_url}/embeddings and returns float vectors."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=timeout,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text (same order)."""
        if not texts:
            return []
        resp = await self._client.post(
            f"{self._base_url}/embeddings",
            json={"model": self.model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        # OpenAI returns data sorted by .index, not necessarily input order.
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    async def aclose(self) -> None:
        await self._client.aclose()


async def build_embedder(session: AsyncSession) -> Embedder:
    """Construct an Embedder from Config Service values."""
    base_url = await config_service.get(
        session, "llm.embedding.base_url", _DEFAULT_BASE_URL
    )
    model = await config_service.get(session, "llm.embedding.model", _DEFAULT_MODEL)
    api_key_env = await config_service.get(session, "llm.embedding.api_key_env", None)
    api_key = os.environ.get(api_key_env) if api_key_env else None
    return Embedder(base_url, model, api_key=api_key)
