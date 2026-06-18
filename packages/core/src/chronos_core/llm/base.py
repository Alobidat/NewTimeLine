"""The provider interface every LLM backend implements (ADR-0014)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from chronos_core.llm.types import LLMResponse


class LLMProvider(ABC):
    """A single LLM backend (cloud or local). Implementations set name/model/is_local."""

    name: str
    model: str
    is_local: bool

    @abstractmethod
    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Run one completion. If ``json_schema`` is given, constrain output to JSON."""

    async def aclose(self) -> None:
        """Release any held resources (HTTP client, etc.). Override if needed."""
        return None
