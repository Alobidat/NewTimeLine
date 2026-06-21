"""Component registry — the self-describing manifest of every backend component the Admin
Portal manages (agents, services, stores).

This is the heart of the portal's extensibility (ADR-0019): the portal renders itself from
these manifests, so **adding a new component = adding a manifest entry here** (plus its
config specs in chronos_core.config_spec). No Admin API or admin-UI code changes are needed
— the new component automatically gets a health card, an auto-generated config form, and
its declared action buttons.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Action verbs a component can declare. The Admin API maps enable/disable/pause to config
# writes; run-now is declared by agents (execution wiring lands with the scheduler).
ACTIONS = ("enable", "disable", "pause", "run-now")


class ComponentManifest(BaseModel):
    """A self-description of one managed component."""

    id: str                                  # stable id, e.g. "agent:enrich"
    kind: str                                # agent | service | store
    title: str
    description: str
    command: str | None = None               # CLI subcommand that runs it (agents)
    config_prefix: str | None = None         # config keys it owns, e.g. "agents.enrich"
    enabled_key: str | None = None           # config key that toggles it on/off
    capabilities: list[str] = Field(default_factory=list)  # "what it can do"
    actions: list[str] = Field(default_factory=list)
    stat_keys: list[str] = Field(default_factory=list)     # notable result counters
    doc: str | None = None


# Built-in components. Append here as the system grows — that is the extension point.
REGISTRY: list[ComponentManifest] = [
    ComponentManifest(
        id="agent:ingest.rss", kind="agent", title="RSS Ingestor",
        description="Polls configured RSS feeds and publishes candidate events (Tier-1, no LLM).",
        command="ingest-rss", config_prefix="agents.ingest.rss",
        enabled_key="agents.ingest.rss.enabled",
        capabilities=["read-feeds", "discover-media"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["feeds", "published", "skipped"], doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:seed.wikidata", kind="agent", title="Wikidata Seeder",
        description="Seeds historical events from Wikidata (Tier-1, no LLM).",
        command="seed-wikidata", capabilities=["seed-history"],
        actions=["run-now"], stat_keys=["fetched", "published", "skipped"],
        doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:seed.iran-us", kind="agent", title="US–Iran PoC Seeder",
        description="Seeds the curated US ↔ Iran history web (events, entities, relations, "
                    "media) for the proof-of-concept journey.",
        command="seed-iran-us", capabilities=["seed-curated"],
        actions=["run-now"], stat_keys=["events", "relations", "new_edges"],
        doc="docs/poc-iran-us.md",
    ),
    ComponentManifest(
        id="agent:enrich", kind="agent", title="Enricher (Tier-2)",
        description="LLM enrichment: summary/category/tags/impact + entities + deep-time refs.",
        command="enrich", config_prefix="agents.enrich",
        enabled_key="agents.enrich.enabled",
        capabilities=["llm-call", "extract-entities", "extract-references"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["candidates", "enriched", "failed"], doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:relate", kind="agent", title="Relation Linker",
        description="Builds the directed history graph from shared entities + time order.",
        command="relate", config_prefix="agents.relate",
        enabled_key="agents.relate.enabled",
        capabilities=["link-graph"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["candidates", "edges"], doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:media.fetch", kind="agent", title="Media Fetcher",
        description="Captures store-disposition media into the object store (ADR-0018).",
        command="media-fetch", config_prefix="agents.media.fetch",
        enabled_key="agents.media.fetch.enabled",
        capabilities=["download-media", "object-store-write"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["candidates", "stored", "external", "failed"], doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:media.check", kind="agent", title="Media Checker",
        description="Re-probes media hosts; applies retention (escalate/pin/release).",
        command="media-check", config_prefix="agents.media.check",
        enabled_key="agents.media.check.enabled",
        capabilities=["probe-hosts", "release-media"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["candidates", "released", "escalated", "pinned", "checked"],
        doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:geocode", kind="agent", title="Geocoder",
        description="Resolves geo_label → PostGIS geometry for events and name → geom for "
                    "place entities via Nominatim (OpenStreetMap). Rate-limited to 1 req/s.",
        command="geocode", config_prefix="agents.geocode",
        enabled_key="agents.geocode.enabled",
        capabilities=["geocode-events", "geocode-entities"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["candidates", "geocoded", "failed"],
        doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:dedup", kind="agent", title="Deduper",
        description="Embeds events via pgvector and merges near-duplicate events "
                    "(cosine similarity, configurable threshold + time window).",
        command="dedup", config_prefix="agents.dedup",
        enabled_key="agents.dedup.enabled",
        capabilities=["embed-events", "merge-duplicates", "vector-search"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["embedded", "pairs_checked", "merged", "skipped"],
        doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:collect", kind="agent", title="On-demand Collector",
        description="Queries all enabled source adapters (Wikipedia/Wikidata/RSS) for a "
                    "searched subject and publishes candidates; prefers media-rich, "
                    "clip-bearing sources first (event-presentation §5.2/§6).",
        command="collect", config_prefix="agents.collect",
        enabled_key="agents.collect.enabled",
        capabilities=["source-adapters", "discover-media", "on-demand"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["adapters", "collected", "published", "skipped"],
        doc="docs/event-presentation.md",
    ),
    ComponentManifest(
        id="agent:media.gap", kind="agent", title="Media-gap Filler",
        description="Finds text-only published events (no image) and re-collects media via the "
                    "clip-bearing adapters — the no-text-only / clips-first policy (ADR-0023).",
        command="media-gap", config_prefix="agents.media.gap",
        enabled_key="agents.media.gap.enabled",
        capabilities=["media-gap", "discover-media", "clips-first"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["candidates", "recollected", "published", "skipped"],
        doc="docs/event-presentation.md",
    ),
    ComponentManifest(
        id="service:llm", kind="service", title="LLM Router",
        description="Provider-agnostic, budget-aware LLM routing (vLLM/Ollama/OpenAI + Claude).",
        config_prefix="llm",
        capabilities=["provider-routing", "budget-fallback"],
        doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="service:severity", kind="service", title="Severity Scorer",
        description="Composite severity blend (impact/social/corroboration).",
        config_prefix="severity", doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="store:postgres", kind="store", title="PostgreSQL + PostGIS",
        description="Canonical relational + geospatial + vector store.",
    ),
    ComponentManifest(
        id="store:object", kind="store", title="Object Store (S3/MinIO)",
        description="Archived media binaries and source snapshots.",
    ),
]

_BY_ID = {m.id: m for m in REGISTRY}


def components(kind: str | None = None) -> list[ComponentManifest]:
    """All manifests, optionally filtered by kind."""
    return [m for m in REGISTRY if kind is None or m.kind == kind]


def get(component_id: str) -> ComponentManifest | None:
    """Look up one manifest by id."""
    return _BY_ID.get(component_id)
