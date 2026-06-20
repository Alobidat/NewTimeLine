"""OpenAI-compatible provider — serves vLLM, Ollama, and OpenAI itself.

All three expose ``POST {base_url}/chat/completions``. For local servers set
``is_local=True`` so the router treats them as the no-cost fallback. ``base_url`` should
include the version segment, e.g. ``http://host:11434/v1`` for Ollama.
"""

from __future__ import annotations

import httpx

from chronos_core.llm.base import LLMProvider
from chronos_core.llm.types import LLMResponse, Usage


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        model: str,
        base_url: str,
        *,
        api_key: str | None = None,
        is_local: bool = True,
        timeout: float = 120.0,
        extra_body: dict | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.is_local = is_local
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        # Server-specific request fields merged into every call, e.g. Ollama's
        # ``{"think": false}`` to stop reasoning models burning the token budget.
        self._extra_body = extra_body or {}
        self._client = httpx.AsyncClient(timeout=timeout)

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **self._extra_body,
        }
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": json_schema, "strict": True},
            }
        resp = await self._client.post(
            f"{self._base_url}/chat/completions", json=body, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"].get("content") or ""
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            usage=Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
            provider=self.name,
            model=self.model,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
