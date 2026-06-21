"""Source-adapter interface (event-presentation.md §6 "Expanding sources").

A **source adapter** wraps one upstream (RSS, Wikidata, Wikipedia full-text, …) behind a
single interface so the on-demand collection agent can query *all enabled* adapters for a
subject without knowing their internals. Each adapter declares its **capabilities** — most
importantly whether it ``yields_clips`` and is ``media_rich`` — so the collector can prefer
clip-bearing, media-rich sources first (the clips-first policy, ADR-0023 / §4).

Adapters return ``normalize.CandidateEvent``/``CandidateMedia`` (the same shape every other
ingestor produces), so collected candidates flow through the unchanged
``publish.publish_candidate`` → enrich → relate → geocode → media pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from chronos_agents.normalize import CandidateEvent


@dataclass(frozen=True)
class SubjectQuery:
    """What the user/agent wants events about: a free-text subject decomposed into the three
    facets the search bar accepts (event-presentation.md §5.1). All optional, but at least one
    should be set; ``text()`` gives the combined query string adapters search with."""

    keyword: str | None = None
    location: str | None = None
    actor: str | None = None

    def text(self) -> str:
        """The combined search string (keyword + actor + location), space-joined, deduped."""
        parts = [p for p in (self.keyword, self.actor, self.location) if p]
        seen: list[str] = []
        for p in parts:
            if p not in seen:
                seen.append(p)
        return " ".join(seen).strip()

    def is_empty(self) -> bool:
        return not self.text()


@dataclass(frozen=True)
class Capabilities:
    """What an adapter can do — used by the collector to order/select adapters.

    ``yields_clips``: can attach video clips (the most-preferred media, ADR-0023).
    ``media_rich``:   typically attaches images/clips (vs. text-only sources).
    ``handles_*``:    which subject facets it can meaningfully search.
    """

    yields_clips: bool = False
    media_rich: bool = False
    handles_keyword: bool = True
    handles_location: bool = True
    handles_actor: bool = True


class SourceAdapter(ABC):
    """One upstream source, behind a uniform collect interface."""

    #: stable adapter id, e.g. ``"rss"`` — matches the ``agents.sources.<id>.enabled`` key.
    id: str = ""
    #: human title for the Admin Portal.
    title: str = ""
    #: declared capabilities; concrete adapters override with their own class attribute.
    capabilities: Capabilities = Capabilities()

    def can_handle(self, subject: SubjectQuery) -> bool:
        """Whether this adapter can collect for ``subject`` given its capabilities."""
        if subject.is_empty():
            return False
        caps = self.capabilities
        if subject.keyword and caps.handles_keyword:
            return True
        if subject.location and caps.handles_location:
            return True
        if subject.actor and caps.handles_actor:
            return True
        return False

    @abstractmethod
    async def collect(self, subject: SubjectQuery, *, limit: int) -> list[CandidateEvent]:
        """Fetch up to ``limit`` candidate events for ``subject``. Network-bound; must not
        raise for an empty result (return ``[]``). Failures are the collector's concern."""
        raise NotImplementedError
