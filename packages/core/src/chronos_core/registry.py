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
        id="agent:seed.video", kind="agent", title="Video Seeder",
        description="Seeds video-hero events (news/history clips) from Wikimedia Commons so the "
                    "video-first feed has real clips, relations, and history for new users.",
        command="seed-video", capabilities=["seed-curated", "seed-media"],
        actions=["run-now"], stat_keys=["events", "chain_edges", "topics"],
        doc="docs/ai-agents.md",
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
        id="agent:persona.gen", kind="agent", title="Persona Generator",
        description="Creates AI-user accounts: LLM-written personas (name/handle/bio/interests) "
                    "with license-clean stock-photo avatars stored in the object store.",
        command="persona-gen", config_prefix="bots.persona_gen",
        capabilities=["llm-call", "create-users", "avatars"],
        actions=["run-now"], stat_keys=["requested", "created", "skipped", "failed"],
        doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:bots.post", kind="agent", title="Persona Poster",
        description="AI users discover license-verified free clips in their interests and "
                    "auto-publish them (after a local-LLM quality/relevance check).",
        command="persona-post", config_prefix="bots",
        enabled_key="bots.posts_enabled",
        capabilities=["discover-media", "llm-call", "auto-publish", "license-gated"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["selected", "posted", "skipped", "rejected", "no_clip"],
        doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:bots.scheduler", kind="agent", title="Bot Scheduler",
        description="Periodic tick: finds overdue AI users (cadence + daily caps) and enqueues "
                    "post/interact jobs, capped per tick. The heartbeat of the living feed.",
        command="bots-tick", config_prefix="bots", enabled_key="bots.enabled",
        capabilities=["schedule", "enqueue"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["due_post", "due_interact", "enqueued"],
        doc="docs/ai-agents.md",
    ),
    ComponentManifest(
        id="agent:bots.interact", kind="agent", title="Persona Interactor",
        description="AI users react to, comment on, and follow each other's in-interest posts "
                    "(local-LLM decisions in the persona's voice).",
        command="persona-interact", config_prefix="bots",
        enabled_key="bots.interacts_enabled",
        capabilities=["llm-call", "react", "comment", "follow"],
        actions=["enable", "disable", "run-now"],
        stat_keys=["selected", "reactions", "comments", "follows", "events_seen"],
        doc="docs/ai-agents.md",
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
