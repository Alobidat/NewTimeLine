"""Budget-aware LLM router with auto-fallback to local (ADR-0015).

Selection per call:
- primary is **local**, or no budget cap, or no fallback → use primary.
- primary is **cloud** and the window's token budget is spent → use the local fallback.
On a primary error, fall back too. Only cloud tokens are charged to the budget.
"""

from __future__ import annotations

import logging

from chronos_core.llm.base import LLMProvider
from chronos_core.llm.budget import BudgetTracker, NullBudget
from chronos_core.llm.types import LLMResponse

log = logging.getLogger("chronos.llm.router")


class LLMRouter:
    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider | None = None,
        *,
        budget: BudgetTracker | None = None,
        max_budget_tokens: int = 0,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.budget = budget or NullBudget()
        self.max_budget_tokens = max_budget_tokens

    async def _select(self) -> LLMProvider:
        # Local primary, no cap, or nothing to fall back to → primary.
        if self.primary.is_local or self.max_budget_tokens <= 0 or self.fallback is None:
            return self.primary
        # Cloud primary with a cap: switch to fallback once the window's budget is spent.
        if await self.budget.used() >= self.max_budget_tokens:
            log.info("cloud budget spent; routing to fallback '%s'", self.fallback.name)
            return self.fallback
        return self.primary

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        provider = await self._select()
        try:
            resp = await provider.complete(
                system=system, user=user, json_schema=json_schema, max_tokens=max_tokens
            )
        except Exception:
            if self.fallback is not None and provider is not self.fallback:
                log.warning(
                    "provider '%s' failed; falling back to '%s'",
                    provider.name,
                    self.fallback.name,
                )
                provider = self.fallback
                resp = await provider.complete(
                    system=system, user=user, json_schema=json_schema, max_tokens=max_tokens
                )
            else:
                raise
        if not provider.is_local:
            await self.budget.add(resp.usage.total)
        return resp

    async def aclose(self) -> None:
        await self.primary.aclose()
        if self.fallback is not None:
            await self.fallback.aclose()
