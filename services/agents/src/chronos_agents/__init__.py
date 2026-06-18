"""chronos_agents — the feed-first agent pipeline (Phase 1: Tier-1, no LLM).

Phase 1 stages: ingest (RSS) → normalize → publish, plus a Wikidata historical seed.
Enrich/dedup/geocode/relation/severity-LLM stages arrive in Phase 3.
"""

__version__ = "0.1.0"
