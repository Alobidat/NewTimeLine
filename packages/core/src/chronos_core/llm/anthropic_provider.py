"""Anthropic (Claude) provider — the optional cloud quality tier."""

from __future__ import annotations

from anthropic import AsyncAnthropic

from chronos_core.llm.base import LLMProvider
from chronos_core.llm.types import LLMResponse, Usage


class AnthropicProvider(LLMProvider):
    """Claude via the official Anthropic SDK. Cloud → counts toward the token budget."""

    is_local = False

    def __init__(self, name: str, model: str, api_key: str | None = None) -> None:
        self.name = name
        self.model = model
        # No api_key → SDK resolves ANTHROPIC_API_KEY from the environment.
        self._client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if json_schema is not None:
            # Structured outputs constrain the response to the schema (Opus 4.8 supports it).
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}
        resp = await self._client.messages.create(**kwargs)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return LLMResponse(
            text=text,
            usage=Usage(resp.usage.input_tokens, resp.usage.output_tokens),
            provider=self.name,
            model=self.model,
        )

    async def aclose(self) -> None:
        await self._client.close()
