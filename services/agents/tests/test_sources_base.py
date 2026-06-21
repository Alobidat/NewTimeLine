"""Pure tests for the source-adapter base: SubjectQuery, can_handle, collector ordering."""

from __future__ import annotations

from chronos_agents.sources.base import Capabilities, SourceAdapter, SubjectQuery
from chronos_agents.sources.collect import _adapter_priority


def test_subject_text_dedups_and_joins_facets():
    s = SubjectQuery(keyword="strike", actor="Iran", location="Iran")
    # facets joined keyword+actor+location, with the duplicate "Iran" collapsed
    assert s.text() == "strike Iran"
    assert s.is_empty() is False
    assert SubjectQuery().is_empty() is True
    assert SubjectQuery().text() == ""


class _Adapter(SourceAdapter):
    def __init__(self, id, caps):
        self.id = id
        self.capabilities = caps

    async def collect(self, subject, *, limit):  # pragma: no cover - not exercised here
        return []


def test_can_handle_respects_capabilities_and_facets():
    a = _Adapter("loc-only", Capabilities(handles_keyword=False, handles_actor=False))
    assert a.can_handle(SubjectQuery(location="Tehran")) is True
    assert a.can_handle(SubjectQuery(keyword="war")) is False
    assert a.can_handle(SubjectQuery()) is False  # empty subject never handled


def test_collector_orders_clip_bearing_media_rich_first():
    rich = _Adapter("wikipedia", Capabilities(yields_clips=True, media_rich=True))
    geo = _Adapter("wikidata", Capabilities(yields_clips=False, media_rich=False))
    rss = _Adapter("rss", Capabilities(yields_clips=False, media_rich=False))
    ordered = sorted([rss, geo, rich], key=_adapter_priority)
    assert ordered[0].id == "wikipedia"  # clip-bearing comes first
