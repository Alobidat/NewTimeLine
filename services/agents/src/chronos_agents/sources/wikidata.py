"""Wikidata source adapter — subject-filtered SPARQL over dated, geolocated events.

Wraps the ``seed_wikidata`` SPARQL + ``normalize.normalize_wikidata`` so subject queries pull
the same dated/geolocated historical events the background seeder does, narrowed to the
subject via a label regex. Geolocated (good for the map) but not media-rich (no clips), so the
collector queries it after the media-rich adapters.
"""

from __future__ import annotations

import logging

import httpx

from chronos_agents.normalize import CandidateEvent, normalize_wikidata
from chronos_agents.seed_wikidata import ENDPOINT, USER_AGENT, _flatten
from chronos_agents.sources.base import Capabilities, SourceAdapter, SubjectQuery

log = logging.getLogger("chronos.agents.sources.wikidata")

# Dated + geolocated events whose English label matches the subject (case-insensitive regex).
_SPARQL = """
SELECT ?event ?eventLabel ?time ?coord ?article WHERE {
  VALUES ?cls { wd:Q178561 wd:Q198 wd:Q8065 wd:Q3839081 wd:Q7944 }
  ?event wdt:P31 ?cls ;
         wdt:P585 ?time ;
         wdt:P625 ?coord ;
         rdfs:label ?eventLabel .
  FILTER(LANG(?eventLabel) = "en")
  FILTER(CONTAINS(LCASE(?eventLabel), LCASE(%(needle)s)))
  OPTIONAL { ?article schema:about ?event ; schema:isPartOf <https://en.wikipedia.org/> . }
}
LIMIT %(limit)d
"""


def _sparql_str(value: str) -> str:
    """Escape a subject string for safe inline use as a SPARQL string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class WikidataAdapter(SourceAdapter):
    """Subject-filtered SPARQL over dated, geolocated Wikidata events."""

    id = "wikidata"
    title = "Wikidata"
    capabilities = Capabilities(yields_clips=False, media_rich=False)

    async def collect(self, subject: SubjectQuery, *, limit: int) -> list[CandidateEvent]:
        needle = subject.text()
        if not needle:
            return []
        query = _SPARQL % {"needle": _sparql_str(needle), "limit": limit}
        headers = {"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"}
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.get(
                    ENDPOINT, params={"query": query, "format": "json"}, headers=headers
                )
                resp.raise_for_status()
                bindings = resp.json()["results"]["bindings"]
        except Exception:
            log.exception("wikidata adapter: query failed for %r", needle)
            return []

        out: list[CandidateEvent] = []
        for binding in bindings:
            cand = normalize_wikidata(_flatten(binding))
            if cand is not None:
                out.append(cand)
        return out[:limit]
