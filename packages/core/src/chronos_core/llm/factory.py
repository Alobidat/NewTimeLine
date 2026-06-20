"""Build the LLM router from Config Service values (ADR-0014/0015).

Everything is config-driven: provider list, models, endpoints, routing, and budget. Add or
switch providers by editing config — no code change.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession

from chronos_core import config_service
from chronos_core.llm.anthropic_provider import AnthropicProvider
from chronos_core.llm.base import LLMProvider
from chronos_core.llm.budget import BudgetTracker, NullBudget, RedisBudget
from chronos_core.llm.openai_compatible import OpenAICompatibleProvider
from chronos_core.llm.router import LLMRouter
from chronos_core.settings import get_settings


def _build_provider(cfg: dict) -> LLMProvider:
    kind = cfg["kind"]
    api_key = os.environ.get(cfg["api_key_env"]) if cfg.get("api_key_env") else None
    if kind == "anthropic":
        return AnthropicProvider(cfg["name"], cfg["model"], api_key=api_key)
    if kind == "openai_compatible":
        return OpenAICompatibleProvider(
            cfg["name"],
            cfg["model"],
            cfg["base_url"],
            api_key=api_key,
            is_local=bool(cfg.get("is_local", True)),
            extra_body=cfg.get("extra_body"),
        )
    raise ValueError(f"unknown llm provider kind: {kind!r}")


async def build_router(session: AsyncSession) -> LLMRouter:
    """Construct an LLMRouter from `llm.providers` / `llm.routing` / `llm.budget` config."""
    providers_cfg = await config_service.get(session, "llm.providers", []) or []
    routing = await config_service.get(session, "llm.routing", {}) or {}
    budget_cfg = await config_service.get(session, "llm.budget", {}) or {}

    by_name = {c["name"]: _build_provider(c) for c in providers_cfg}
    primary = by_name[routing["primary"]]
    fallback_name = routing.get("fallback")
    fallback = by_name.get(fallback_name) if fallback_name else None

    max_tokens = int(budget_cfg.get("max_tokens", 0))
    window = int(budget_cfg.get("window_seconds", 86400))
    budget: BudgetTracker = NullBudget()
    if max_tokens > 0:
        import redis.asyncio as aioredis  # only needed when a cloud budget is enforced

        budget = RedisBudget(aioredis.from_url(get_settings().redis_url), window)

    return LLMRouter(primary, fallback, budget=budget, max_budget_tokens=max_tokens)
