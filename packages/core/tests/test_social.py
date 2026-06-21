"""Unit tests for the social substrate (Phase 4-B): DTO validation + the branching logic in
chronos_core.social_repo (follow self-loop + dedup, promote upsert/clear, activity guard) and
the pure interest-profile scoring math (decay + accumulation).

Pure-logic: a tiny in-memory fake session stands in for AsyncSession so we exercise the
helpers without a database (the project has no DB test fixture). Aggregate-read helpers that
emit raw SQL are covered by the integration suite, not here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from chronos_core import social_repo as repo
from chronos_core.interest import _Acc, accumulate, decay_factor
from chronos_core.models.social import ActivityLog, Follow, Promote
from chronos_core.schemas.social import PromoteCast
from pydantic import ValidationError


# --- a minimal in-memory async "session" ---------------------------------------------


class FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class FakeSession:
    """Supports the get/add/delete/execute(delete-stmt) subset social_repo branches on."""

    def __init__(self) -> None:
        self.objects: list[object] = []

    def _pk(self, obj):
        if isinstance(obj, Follow):
            return ("Follow", obj.user_id, obj.target_type, obj.target_id)
        if isinstance(obj, Promote):
            return ("Promote", obj.user_id, obj.target_type, obj.target_id)
        return None

    async def get(self, model, key):
        name = model.__name__
        target = (name, *key) if isinstance(key, tuple) else (name, key)
        for obj in self.objects:
            if self._pk(obj) == target:
                return obj
        return None

    def add(self, obj) -> None:
        self.objects.append(obj)

    async def delete(self, obj) -> None:
        self.objects.remove(obj)

    async def flush(self) -> None:
        return None

    async def execute(self, stmt):
        values = set(str(v) for v in stmt.compile().params.values())
        before = len(self.objects)
        self.objects = [
            o
            for o in self.objects
            if not (
                isinstance(o, Follow)
                and str(o.user_id) in values
                and str(o.target_type) in values
                and str(o.target_id) in values
            )
        ]
        return FakeResult(before - len(self.objects))


# --- DTO validation -------------------------------------------------------------------


def test_promote_cast_rejects_out_of_range_value():
    with pytest.raises(ValidationError):
        PromoteCast(target_type="event", target_id=uuid.uuid4(), value=2)
    with pytest.raises(ValidationError):
        PromoteCast(target_type="nope", target_id=uuid.uuid4(), value=1)
    assert PromoteCast(target_type="relation", target_id=uuid.uuid4(), value=-1).value == -1


# --- follows --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follow_dedups_and_rejects_self():
    s = FakeSession()
    me, other = uuid.uuid4(), uuid.uuid4()
    assert await repo.follow(s, user_id=me, target_type="user", target_id=other) is True
    # Idempotent.
    assert await repo.follow(s, user_id=me, target_type="user", target_id=other) is False
    # Self-follow rejected.
    with pytest.raises(ValueError):
        await repo.follow(s, user_id=me, target_type="user", target_id=me)
    # Bad target type rejected.
    with pytest.raises(ValueError):
        await repo.follow(s, user_id=me, target_type="planet", target_id=other)


@pytest.mark.asyncio
async def test_unfollow_removes_edge():
    s = FakeSession()
    me, ent = uuid.uuid4(), uuid.uuid4()
    await repo.follow(s, user_id=me, target_type="entity", target_id=ent)
    assert await repo.unfollow(s, user_id=me, target_type="entity", target_id=ent) is True
    assert not any(isinstance(o, Follow) for o in s.objects)
    # Removing again is a no-op.
    assert await repo.unfollow(s, user_id=me, target_type="entity", target_id=ent) is False


# --- promotes -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_upsert_then_clear():
    s = FakeSession()
    me, ev = uuid.uuid4(), uuid.uuid4()
    assert await repo.cast_promote(s, user_id=me, target_type="event", target_id=ev, value=1) == 1
    # Change to a demote in place (no duplicate row).
    assert await repo.cast_promote(s, user_id=me, target_type="event", target_id=ev, value=-1) == -1
    assert sum(isinstance(o, Promote) for o in s.objects) == 1
    # value=0 clears the vote.
    assert await repo.cast_promote(s, user_id=me, target_type="event", target_id=ev, value=0) == 0
    assert not any(isinstance(o, Promote) for o in s.objects)


@pytest.mark.asyncio
async def test_promote_rejects_bad_target_and_value():
    s = FakeSession()
    with pytest.raises(ValueError):
        await repo.cast_promote(s, user_id=uuid.uuid4(), target_type="moon", target_id=uuid.uuid4(), value=1)
    with pytest.raises(ValueError):
        await repo.cast_promote(s, user_id=uuid.uuid4(), target_type="event", target_id=uuid.uuid4(), value=5)


# --- activity -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_activity_guards_unknown_kind():
    s = FakeSession()
    # Unknown kind/target → ignored (returns None), never raises.
    assert await repo.record_activity(
        s, user_id=uuid.uuid4(), kind="teleport", target_type="event", target_id=uuid.uuid4()
    ) is None
    # Known kind → an ActivityLog row with the per-kind default weight.
    row = await repo.record_activity(
        s, user_id=uuid.uuid4(), kind="promote", target_type="event", target_id=uuid.uuid4()
    )
    assert isinstance(row, ActivityLog)
    assert row.weight == repo.default_weight("promote") == 3.0


# --- interest scoring math ------------------------------------------------------------


def test_decay_factor_halves_each_half_life():
    assert decay_factor(0, 14) == pytest.approx(1.0)
    assert decay_factor(14, 14) == pytest.approx(0.5)
    assert decay_factor(28, 14) == pytest.approx(0.25)
    # Non-positive half-life disables decay.
    assert decay_factor(100, 0) == 1.0


def test_accumulate_sums_weighted_facets():
    acc = _Acc()
    e1, e2, p1, s1 = "e1", "e2", "p1", "s1"
    accumulate(acc, decayed_weight=2.0, category="war", entity_ids=[e1, e2], place_ids=[p1], source_ids=[s1])
    accumulate(acc, decayed_weight=1.0, category="war", entity_ids=[e1], place_ids=[], source_ids=[])
    assert acc.n == 2
    assert acc.categories["war"] == pytest.approx(3.0)
    assert acc.entities[e1] == pytest.approx(3.0)
    assert acc.entities[e2] == pytest.approx(2.0)
    assert acc.places[p1] == pytest.approx(2.0)
    assert acc.sources[s1] == pytest.approx(2.0)


def test_recent_activity_outweighs_old_via_decay():
    # An old like decays below a fresh view of the same weight, given the same half-life.
    now = datetime.now(timezone.utc)
    fresh = decay_factor((now - now).total_seconds() / 86400.0, 14)
    old = decay_factor((now - (now - timedelta(days=42))).total_seconds() / 86400.0, 14)
    assert fresh > old
