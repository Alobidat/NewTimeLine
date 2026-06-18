"""Historical seed from Wikidata (Tier-1, no LLM).

Pulls dated, geolocated historical events (battles/wars/disasters) via SPARQL to populate
deep time + the map. Each becomes an event sourced from its Wikipedia/Wikidata page.
"""

from __future__ import annotations

import logging

import httpx
from chronos_core.db import session_scope

from chronos_agents.normalize import normalize_wikidata
from chronos_agents.publish import load_weights, publish_candidate

log = logging.getLogger("chronos.agents.seed_wikidata")
AGENT = "seed:wikidata"

ENDPOINT = "https://query.wikidata.org/sparql"
# Required by Wikidata's etiquette policy.
USER_AGENT = "ChronosNewTimeLine/0.1 (https://github.com/Alobidat/NewTimeLine)"

# Dated + geolocated historical events across a few notable classes.
SPARQL = """
SELECT ?event ?eventLabel ?time ?coord ?article WHERE {
  VALUES ?cls { wd:Q178561 wd:Q198 wd:Q8065 wd:Q3839081 wd:Q7944 }
  ?event wdt:P31 ?cls ;
         wdt:P585 ?time ;
         wdt:P625 ?coord .
  OPTIONAL { ?article schema:about ?event ; schema:isPartOf <https://en.wikipedia.org/> . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT %(limit)d
"""


def _flatten(binding: dict) -> dict:
    """SPARQL binding → plain {key: value} (label key normalized to 'label')."""
    row = {k: v.get("value") for k, v in binding.items()}
    row["label"] = row.get("eventLabel")
    return row


async def seed_wikidata(limit: int = 300) -> dict:
    """Fetch + publish up to ``limit`` historical events. Returns a summary of counts."""
    query = SPARQL % {"limit": limit}
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.get(
            ENDPOINT,
            params={"query": query, "format": "json"},
            headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
        )
        resp.raise_for_status()
        bindings = resp.json()["results"]["bindings"]

    totals = {"fetched": len(bindings), "published": 0, "skipped": 0}
    async with session_scope() as session:
        weights = await load_weights(session)
        for binding in bindings:
            cand = normalize_wikidata(_flatten(binding))
            event = (
                await publish_candidate(session, cand, agent_name=AGENT, weights=weights)
                if cand
                else None
            )
            totals["published" if event is not None else "skipped"] += 1
    log.info("wikidata seed: %s", totals)
    return totals
