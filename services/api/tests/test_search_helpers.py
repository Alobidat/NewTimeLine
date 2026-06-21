"""Unit tests for the faceted-search router helpers (ADR-0022).

These cover the pure subject/args derivation and the Redis-enqueue path (mirrors admin
run-now) with a fake Redis client — no DB or network. Async router handlers that need a
session are exercised by the integration suite, not here.
"""

from __future__ import annotations

import json
from collections import deque

import chronos_api.routers.search as search_router
from chronos_api.routers.search import _collect_args, _enqueue_collect, _subject_text
from chronos_core.run_queue import QUEUE_KEY


class _FakeRedis:
    """Minimal Redis stub: records lpush calls and supports close()."""

    def __init__(self) -> None:
        self._lists: dict[str, deque] = {}
        self.closed = False

    def lpush(self, key: str, value: str) -> None:
        self._lists.setdefault(key, deque()).appendleft(value)

    def close(self) -> None:
        self.closed = True


def test_subject_text_dedups_and_joins_like_subjectquery():
    # keyword + actor + location, deduped, space-joined (matches SubjectQuery.text()).
    assert _subject_text("strike", "Iran", "Iran") == "strike Iran"
    assert _subject_text("strike", None, None) == "strike"
    assert _subject_text(None, None, None) == ""
    assert _subject_text(None, "Tehran", "Iran") == "Iran Tehran"


def test_collect_args_only_includes_set_facets():
    assert _collect_args("strike", None, None) == {"keyword": "strike"}
    assert _collect_args(None, "Iran", "Tehran") == {
        "location": "Iran",
        "actor": "Tehran",
    }
    assert _collect_args(None, None, None) == {}


def test_enqueue_collect_pushes_collect_job(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(
        search_router.redislib, "from_url", lambda _url: fake
    )
    ok = _enqueue_collect({"keyword": "strike"})
    assert ok is True
    assert fake.closed is True
    # Exactly one job queued, command "collect", carrying the subject args.
    payload = fake._lists[QUEUE_KEY][0]
    job = json.loads(payload)
    assert job == {"command": "collect", "args": {"keyword": "strike"}}


def test_enqueue_collect_swallows_redis_errors(monkeypatch):
    def _boom(_url):
        raise RuntimeError("no redis")

    monkeypatch.setattr(search_router.redislib, "from_url", _boom)
    # Must never raise into the request path; returns False instead.
    assert _enqueue_collect({"keyword": "x"}) is False
