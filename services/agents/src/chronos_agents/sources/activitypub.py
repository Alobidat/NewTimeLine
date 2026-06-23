"""ActivityPub source adapter — federated video from the fediverse (PeerTube).

PeerTube is the ActivityPub video platform; its videos are ActivityStreams 2.0 ``Video``
objects carrying direct, CORS-friendly mp4/HLS files — exactly the browser-playable clips the
video-first feed wants, and freely federated (no scraping). This adapter:

1. **discovers** videos for a subject via SepiaSearch — PeerTube's official meta-search that
   indexes the whole PeerTube fediverse (so one query reaches many instances), and
2. **fetches each video's ActivityPub object** (content-negotiated with
   ``Accept: application/activity+json``) and normalizes the AS2 ``Video`` into the same
   ``CandidateEvent`` every ingestor produces (``normalize.normalize_activitypub_video``).

Candidates flow through the unchanged ``publish.publish_candidate`` → enrich → relate → media
pipeline; the clip becomes a hero video (``discover_media`` links it, so ``/media/{id}/raw``
redirects to the PeerTube file and the client plays it instantly). Clip-bearing + media-rich,
so the collector queries it first (clips-first, ADR-0023/0024). Enabled via
``agents.sources.activitypub.enabled`` (config; default True).
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from chronos_agents.normalize import CandidateEvent, normalize_activitypub_video
from chronos_agents.sources import wikimedia
from chronos_agents.sources.base import Capabilities, SourceAdapter, SubjectQuery

log = logging.getLogger("chronos.agents.sources.activitypub")

# Default discovery endpoint: SepiaSearch federates across PeerTube instances. Overridable via
# ``agents.sources.activitypub.search_url`` (e.g. point at a single trusted instance's API).
DEFAULT_SEARCH_URL = "https://sepiasearch.org"

# Ask upstreams for the ActivityStreams representation (the AS2 Video object).
_AP_ACCEPT = (
    'application/activity+json, '
    'application/ld+json; profile="https://www.w3.org/ns/activitystreams"'
)


class ActivityPubAdapter(SourceAdapter):
    """Subject search across the PeerTube fediverse, yielding clip-hero candidate events."""

    id = "activitypub"
    title = "Fediverse video (PeerTube)"
    capabilities = Capabilities(yields_clips=True, media_rich=True)

    def __init__(
        self,
        *,
        search_url: str = DEFAULT_SEARCH_URL,
        max_clip_width: int = 720,
        max_duration_s: int = 600,
    ):
        self.search_url = search_url.rstrip("/")
        self.max_clip_width = max_clip_width
        # Skip long videos so the short-form feed stays clip-shaped (0/None = no cap).
        self.max_duration_s = max_duration_s

    async def _search(
        self, client: httpx.AsyncClient, query: str, count: int
    ) -> list[dict]:
        """SepiaSearch / PeerTube video search → the raw result dicts (each has a watch ``url``)."""
        params = {
            "search": query,
            "count": str(count),
            "sort": "-match",     # most relevant first
            "nsfw": "false",      # exclude adult content
            "isLive": "false",    # clips, not livestreams
        }
        if self.max_duration_s:
            params["durationMax"] = str(self.max_duration_s)
        resp = await client.get(
            f"{self.search_url}/api/v1/search/videos", params=params, timeout=15.0
        )
        resp.raise_for_status()
        return resp.json().get("data", []) or []

    async def _fetch_as2(self, client: httpx.AsyncClient, url: str) -> dict | None:
        """Fetch a video's ActivityStreams ``Video`` object (the ActivityPub representation)."""
        resp = await client.get(url, headers={"Accept": _AP_ACCEPT}, timeout=15.0)
        resp.raise_for_status()
        obj = resp.json()
        return obj if isinstance(obj, dict) else None

    async def collect(self, subject: SubjectQuery, *, limit: int) -> list[CandidateEvent]:
        query = subject.text()
        if not query:
            return []
        # Over-fetch a little: some results fail AS2 fetch or carry no playable mp4.
        count = max(limit, 5) + limit
        out: list[CandidateEvent] = []
        async with httpx.AsyncClient(
            headers={"User-Agent": wikimedia.USER_AGENT}, follow_redirects=True
        ) as client:
            try:
                results = await self._search(client, query, count)
            except Exception:
                log.exception("activitypub adapter: search failed for %r", query)
                return []
            for r in results:
                if len(out) >= limit:
                    break
                watch = r.get("url") or r.get("id")
                if not isinstance(watch, str) or not watch:
                    continue
                try:
                    obj = await self._fetch_as2(client, watch)
                except Exception:
                    log.warning("activitypub adapter: AS2 fetch failed: %s", watch)
                    continue
                if obj is None:
                    continue
                host = (r.get("account") or {}).get("host") or urlparse(watch).netloc or None
                cand = normalize_activitypub_video(
                    obj,
                    instance_host=host,
                    max_clip_width=self.max_clip_width,
                    max_duration_s=self.max_duration_s,
                )
                if cand is not None:
                    out.append(cand)
        return out[:limit]
