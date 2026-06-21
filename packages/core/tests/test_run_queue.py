"""Tests for run_queue push/pop using a fake Redis stub."""

from __future__ import annotations

import json
from collections import deque

import pytest

from chronos_core.run_queue import QUEUE_KEY, pop_job, push_job


class _FakeRedis:
    """Minimal Redis stub that supports lpush + brpop on a single list key."""

    def __init__(self) -> None:
        self._lists: dict[str, deque] = {}

    def lpush(self, key: str, value: str) -> None:
        self._lists.setdefault(key, deque()).appendleft(value)

    def brpop(self, key: str, timeout: float = 0):
        lst = self._lists.get(key)
        if not lst:
            return None
        return (key, lst.pop())


def test_push_pop_roundtrip():
    r = _FakeRedis()
    push_job(r, "ingest-rss")
    job = pop_job(r)
    assert job == {"command": "ingest-rss", "args": {}}


def test_push_with_extra_args():
    r = _FakeRedis()
    push_job(r, "seed-wikidata", {"limit": 50})
    job = pop_job(r)
    assert job["command"] == "seed-wikidata"
    assert job["args"] == {"limit": 50}


def test_pop_empty_returns_none():
    r = _FakeRedis()
    assert pop_job(r, timeout=0) is None


def test_fifo_order():
    r = _FakeRedis()
    push_job(r, "ingest-rss")
    push_job(r, "enrich")
    first = pop_job(r)
    second = pop_job(r)
    assert first["command"] == "ingest-rss"
    assert second["command"] == "enrich"


def test_queue_key_constant():
    assert QUEUE_KEY == "chronos:run_queue"
