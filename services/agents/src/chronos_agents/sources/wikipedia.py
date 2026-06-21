"""Wikipedia full-text source adapter — the media-rich, clip-bearing source (ADR-0023).

Searches Wikipedia's full text (``action=query&list=search``) for the subject, then for each
hit attaches the article's **lead image** as the hero and its first **WebM clip** (via the
shared ``wikimedia`` helpers) — so collected events are media-rich and prefer clips, exactly
what the no-text-only / clips-first policy wants. This is the source the collector queries
first (``media_rich=True``, ``yields_clips=True``).

Each hit becomes a ``CandidateEvent`` timed to the article's snippet/now; the enricher refines
time/summary later. The source URL is the canonical ``/wiki/<Title>`` page so the existing
source-URL dedup in ``publish_candidate`` works.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from chronos_core.domain.temporal import TimePrecision, datetime_to_t

from chronos_agents.normalize import CandidateEvent, CandidateMedia
from chronos_agents.sources import wikimedia
from chronos_agents.sources.base import Capabilities, SourceAdapter, SubjectQuery

log = logging.getLogger("chronos.agents.sources.wikipedia")

_API_URL = "https://en.wikipedia.org/w/api.php"
_WIKI_BASE = "https://en.wikipedia.org/wiki/"


def _strip_html(text: str | None) -> str | None:
    """Drop the <span class="searchmatch"> markup Wikipedia wraps around hit terms."""
    if not text:
        return None
    out, depth = [], 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out).strip() or None


def _article_url(title: str) -> str:
    return _WIKI_BASE + title.replace(" ", "_")


class WikipediaAdapter(SourceAdapter):
    """Full-text Wikipedia search with lead-image hero + WebM clip per hit."""

    id = "wikipedia"
    title = "Wikipedia (full-text)"
    capabilities = Capabilities(yields_clips=True, media_rich=True)

    async def _search(
        self, client: httpx.AsyncClient, query: str, limit: int
    ) -> list[dict]:
        resp = await client.get(
            _API_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": str(limit),
                "format": "json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json().get("query", {}).get("search", []) or []

    async def collect(self, subject: SubjectQuery, *, limit: int) -> list[CandidateEvent]:
        query = subject.text()
        if not query:
            return []
        now = datetime.now(UTC)
        out: list[CandidateEvent] = []
        async with httpx.AsyncClient(headers={"User-Agent": wikimedia.USER_AGENT}) as client:
            try:
                hits = await self._search(client, query, limit)
            except Exception:
                log.exception("wikipedia adapter: search failed for %r", query)
                return []
            for hit in hits:
                title = hit.get("title")
                if not title:
                    continue
                source_url = _article_url(title)
                media: list[CandidateMedia] = []
                # Lead image → hero (publish.publish_candidate makes the first image the hero).
                try:
                    image = await wikimedia.wiki_image(client, source_url)
                except Exception:
                    image = None
                if image:
                    media.append(CandidateMedia("image", image))
                # WebM clip → gallery (clips-first, ADR-0023).
                try:
                    clip = await wikimedia.wiki_video(client, source_url)
                except Exception:
                    clip = None
                if clip:
                    clip_url, _caption = clip
                    media.append(CandidateMedia("video", clip_url, "video/webm"))
                out.append(
                    CandidateEvent(
                        title=title,
                        summary=_strip_html(hit.get("snippet")),
                        t_start=datetime_to_t(now),
                        time_precision=TimePrecision.DAY,
                        instant=now,
                        category="history",
                        source_url=source_url,
                        source_title=title,
                        source_publisher="Wikipedia",
                        source_kind="encyclopedia",
                        media=media,
                    )
                )
        return out[:limit]
