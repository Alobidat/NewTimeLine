"""Tests for the budget-aware LLM router (ADR-0015) using fake providers."""

from chronos_core.llm.base import LLMProvider
from chronos_core.llm.budget import InMemoryBudget
from chronos_core.llm.router import LLMRouter
from chronos_core.llm.types import LLMResponse, Usage


class FakeProvider(LLMProvider):
    def __init__(self, name, is_local, tokens=100, fail=False):
        self.name = name
        self.model = "m"
        self.is_local = is_local
        self._tokens = tokens
        self._fail = fail
        self.calls = 0

    async def complete(self, *, system, user, json_schema=None, max_tokens=1024):
        self.calls += 1
        if self._fail:
            raise RuntimeError("provider down")
        return LLMResponse("ok", Usage(self._tokens, 0), self.name, self.model)

    async def aclose(self):
        return None


async def test_local_primary_never_charges_budget():
    primary = FakeProvider("ollama", is_local=True)
    cloud = FakeProvider("claude", is_local=False)
    budget = InMemoryBudget(3600)
    router = LLMRouter(primary, cloud, budget=budget, max_budget_tokens=50)

    resp = await router.complete(system="s", user="u")
    assert resp.provider == "ollama"
    assert primary.calls == 1 and cloud.calls == 0
    assert await budget.used() == 0  # local tokens never counted


async def test_cloud_primary_charges_then_switches_to_local_when_spent():
    cloud = FakeProvider("claude", is_local=False, tokens=100)
    local = FakeProvider("ollama", is_local=True)
    budget = InMemoryBudget(3600)
    router = LLMRouter(cloud, local, budget=budget, max_budget_tokens=150)

    r1 = await router.complete(system="s", user="u")  # used 0 < 150 → cloud, charge 100
    r2 = await router.complete(system="s", user="u")  # used 100 < 150 → cloud, charge 200
    r3 = await router.complete(system="s", user="u")  # used 200 >= 150 → local fallback

    assert [r1.provider, r2.provider, r3.provider] == ["claude", "claude", "ollama"]
    assert cloud.calls == 2 and local.calls == 1
    assert await budget.used() == 200  # only the two cloud calls counted


async def test_no_budget_cap_always_uses_cloud_primary():
    cloud = FakeProvider("claude", is_local=False)
    local = FakeProvider("ollama", is_local=True)
    router = LLMRouter(cloud, local, budget=InMemoryBudget(3600), max_budget_tokens=0)

    for _ in range(3):
        assert (await router.complete(system="s", user="u")).provider == "claude"
    assert local.calls == 0


async def test_error_falls_back_to_local():
    cloud = FakeProvider("claude", is_local=False, fail=True)
    local = FakeProvider("ollama", is_local=True)
    router = LLMRouter(cloud, local, budget=InMemoryBudget(3600), max_budget_tokens=0)

    resp = await router.complete(system="s", user="u")
    assert resp.provider == "ollama"
    assert cloud.calls == 1 and local.calls == 1


async def test_error_with_no_fallback_raises():
    cloud = FakeProvider("claude", is_local=False, fail=True)
    router = LLMRouter(cloud, None)
    import pytest

    with pytest.raises(RuntimeError):
        await router.complete(system="s", user="u")
