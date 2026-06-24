"""Unit tests for the For-You diversity re-rank (chronos_api.feed_queries._diversify).

Pure function: it reorders score-ranked feed items so clips sharing a creator/entity (else
category) are spaced out, so one tightly-linked cluster (e.g. the NASA Apollo set) can't
dominate a page. No DB.
"""

from __future__ import annotations

import uuid

from chronos_core.schemas.event import EventRead
from chronos_core.schemas.interaction import CommentAuthor
from chronos_core.schemas.social import FeedItem

from chronos_api.feed_queries import _diversify


def _item(author_name: str | None, category: str | None = None) -> FeedItem:
    ev = EventRead(
        id=uuid.uuid4(), title="t", t_start=2020.0, t_end=2020.0,
        time_precision="day", severity=0, confidence=0, source_count=0,
        status="published", category=category,
    )
    author = (
        CommentAuthor(id=uuid.uuid4(), handle=author_name, display_name=author_name)
        if author_name else None
    )
    return FeedItem(event=ev, author=author)


def _keys(items: list[FeedItem]) -> list[str]:
    return [(it.author.handle if it.author else (it.event.category or "?")) for it in items]


def test_diversify_spaces_out_a_dominant_cluster():
    # 6 NASA + 2 SpaceX + 1 ESA, all from the same author-id per name.
    nasa = CommentAuthor(id=uuid.uuid4(), handle="NASA", display_name="NASA")
    spacex = CommentAuthor(id=uuid.uuid4(), handle="SpaceX", display_name="SpaceX")
    esa = CommentAuthor(id=uuid.uuid4(), handle="ESA", display_name="ESA")

    def mk(a):
        ev = EventRead(id=uuid.uuid4(), title="t", t_start=2020.0, t_end=2020.0,
                       time_precision="day", severity=0, confidence=0, source_count=0,
                       status="published")
        return FeedItem(event=ev, author=a)

    items = [mk(nasa)] * 6 + [mk(spacex)] * 2 + [mk(esa)]
    out = _diversify(items, gap=2)
    keys = [it.author.handle for it in out]
    # No two NASA clips are adjacent while other authors remain to interleave.
    first_six = keys[:6]
    assert not any(
        first_six[i] == first_six[i + 1] == "NASA" for i in range(len(first_six) - 1)
    ), first_six
    # All items are preserved (nothing dropped).
    assert sorted(keys) == sorted(["NASA"] * 6 + ["SpaceX"] * 2 + ["ESA"])


def test_diversify_falls_back_to_category_without_author():
    items = [_item(None, "news"), _item(None, "news"), _item(None, "sports"),
             _item(None, "news")]
    out = _diversify(items, gap=2)
    keys = _keys(out)
    # The lone 'sports' is pulled up between 'news' items rather than staying last.
    assert keys[1] == "sports", keys


def test_diversify_preserves_order_when_all_distinct():
    items = [_item("a"), _item("b"), _item("c")]
    assert _keys(_diversify(items)) == ["a", "b", "c"]
