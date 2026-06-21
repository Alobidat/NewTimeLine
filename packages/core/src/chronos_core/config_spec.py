"""Config specs — typed, self-describing metadata for every config key.

This is the single source of truth for runtime config (ADR-0019): each key declares its
type, default, scope, owning component, UI label/help, and constraints. The Admin Portal
**auto-generates a validated form** from these specs, the Admin API validates writes against
them, and chronos_core.config_service derives its seed DEFAULTS from them — so adding a
tunable in one place makes it seedable, editable, and validated everywhere.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# default LLM providers (see ADR-0014/0015); kept verbatim as the seeded value.
_LLM_PROVIDERS = [
    {
        "name": "ollama", "kind": "openai_compatible",
        "base_url": "http://host.docker.internal:11434/v1", "model": "llama3.1",
        "is_local": True, "api_key_env": None,
    },
    {
        "name": "claude", "kind": "anthropic", "base_url": None,
        "model": "claude-opus-4-8", "is_local": False, "api_key_env": "ANTHROPIC_API_KEY",
    },
]
_RSS_FEEDS = [
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.theguardian.com/world/rss",
    "https://www.aljazeera.com/xml/rss/all.xml",
]


class ConfigSpec(BaseModel):
    """Type + metadata + constraints for one config key."""

    key: str
    type: str                      # bool | int | float | string | enum | list | json
    scope: str
    default: Any
    label: str
    help: str = ""
    component_id: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] | None = None
    secret: bool = False


def _i(key, default, label, *, scope, component_id, help="", minimum=None, maximum=None):
    return ConfigSpec(key=key, type="int", scope=scope, default=default, label=label,
                      help=help, component_id=component_id, minimum=minimum, maximum=maximum)


def _b(key, default, label, *, scope, component_id, help=""):
    return ConfigSpec(key=key, type="bool", scope=scope, default=default, label=label,
                      help=help, component_id=component_id)


SPECS: list[ConfigSpec] = [
    ConfigSpec(key="severity.weights", type="json", scope="severity", default={
        "impact": 0.5, "social": 0.2, "corroboration": 0.3},
        label="Severity weights", component_id="service:severity",
        help="Blend weights for the composite severity score."),

    # RSS ingestor
    ConfigSpec(key="agents.ingest.rss.feeds", type="list", scope="agent:ingest",
               default=_RSS_FEEDS, label="RSS feeds", component_id="agent:ingest.rss",
               help="Feed URLs polled each run."),
    _b("agents.ingest.rss.enabled", True, "Enabled",
       scope="agent:ingest", component_id="agent:ingest.rss"),
    _i("agents.ingest.rss.max_items_per_feed", 50, "Max items per feed",
       scope="agent:ingest", component_id="agent:ingest.rss", minimum=1, maximum=500),

    # LLM layer
    ConfigSpec(key="llm.providers", type="json", scope="llm", default=_LLM_PROVIDERS,
               label="Providers", component_id="service:llm",
               help="Pluggable LLM providers; openai_compatible serves vLLM/Ollama/OpenAI."),
    ConfigSpec(key="llm.routing", type="json", scope="llm",
               default={"primary": "ollama", "fallback": "claude"},
               label="Routing", component_id="service:llm",
               help="Primary provider + fallback used on budget-exhaustion/error."),
    ConfigSpec(key="llm.budget", type="json", scope="llm",
               default={"window_seconds": 86400, "max_tokens": 0},
               label="Cloud token budget", component_id="service:llm",
               help="max_tokens=0 disables the cap (local primary needs none)."),

    # Enricher
    _b("agents.enrich.enabled", True, "Enabled", scope="agent:enrich", component_id="agent:enrich"),
    _i("agents.enrich.batch_size", 20, "Batch size",
       scope="agent:enrich", component_id="agent:enrich", minimum=1, maximum=200),
    _i("agents.enrich.max_tokens", 800, "Max tokens / call",
       scope="agent:enrich", component_id="agent:enrich", minimum=64, maximum=8192),

    # Relation linker
    _b("agents.relate.enabled", True, "Enabled", scope="agent:relate", component_id="agent:relate"),
    _i("agents.relate.batch_size", 50, "Batch size",
       scope="agent:relate", component_id="agent:relate", minimum=1, maximum=500),
    _i("agents.relate.min_shared", 1, "Min shared entities",
       scope="agent:relate", component_id="agent:relate", minimum=1, maximum=10,
       help="Minimum shared entities for two events to be linked."),
    _i("agents.relate.max_neighbors", 200, "Max neighbors / event",
       scope="agent:relate", component_id="agent:relate", minimum=1, maximum=2000),

    # Media archival
    _b("agents.media.fetch.enabled", True, "Fetch enabled",
       scope="agent:media", component_id="agent:media.fetch"),
    _i("agents.media.fetch.batch_size", 20, "Fetch batch size",
       scope="agent:media", component_id="agent:media.fetch", minimum=1, maximum=200),
    _i("agents.media.fetch.max_bytes", 26_214_400, "Max bytes to store",
       scope="agent:media", component_id="agent:media.fetch", minimum=0,
       help="Binaries larger than this stay linked rather than stored."),
    _b("agents.media.check.enabled", True, "Check enabled",
       scope="agent:media", component_id="agent:media.check"),
    _i("agents.media.check.batch_size", 50, "Check batch size",
       scope="agent:media", component_id="agent:media.check", minimum=1, maximum=500),
    _i("agents.media.check.recheck_hours", 24, "Re-check interval (hours)",
       scope="agent:media", component_id="agent:media.check", minimum=1, maximum=720),
    _i("agents.media.release_threshold", 70, "Release threshold",
       scope="agent:media", component_id="agent:media.check", minimum=0, maximum=100,
       help="persistence_confidence at/above which a durable archive may be released."),

    # Deduper (pgvector cosine similarity, Phase 3b)
    _b("agents.dedup.enabled", True, "Enabled",
       scope="agent:dedup", component_id="agent:dedup"),
    _i("agents.dedup.batch_size", 50, "Batch size",
       scope="agent:dedup", component_id="agent:dedup", minimum=1, maximum=500,
       help="Events to embed (and dedup-check) per run."),
    ConfigSpec(key="agents.dedup.similarity_threshold", type="float",
               scope="agent:dedup", component_id="agent:dedup",
               default=0.95, label="Similarity threshold",
               minimum=0.5, maximum=1.0,
               help="Cosine similarity at/above which two events are merged as duplicates."),
    ConfigSpec(key="agents.dedup.time_window_years", type="float",
               scope="agent:dedup", component_id="agent:dedup",
               default=1.0, label="Time window (years)",
               minimum=0.0, maximum=100.0,
               help="Events must be within this many years of each other to be considered "
                    "duplicates (prevents merging same-title events from different eras)."),

    # Geocoder (Nominatim / OSM, Phase 3b)
    _b("agents.geocode.enabled", True, "Enabled",
       scope="agent:geocode", component_id="agent:geocode"),
    _i("agents.geocode.batch_size", 20, "Batch size",
       scope="agent:geocode", component_id="agent:geocode", minimum=2, maximum=200,
       help="Events + place entities to geocode per run. Nominatim is rate-limited to "
            "~1 req/s so keep this low unless running on a private instance."),
    _b("agents.geocode.cascade", True, "Location cascade",
       scope="agent:geocode", component_id="agent:geocode",
       help="When geo_label lookup fails, resolve via location entities → text analysis "
            "→ news-agency country so every event gets a location (ADR-0020)."),
    _b("agents.geocode.agency_fallback", True, "News-agency fallback",
       scope="agent:geocode", component_id="agent:geocode",
       help="Last resort: place the event at the source/news-agency's country when nothing "
            "else resolves. Weakest signal; disable to leave such events unresolved."),

    # Embedding provider (used by the Deduper; see chronos_core.llm.embedder)
    ConfigSpec(key="llm.embedding.base_url", type="string",
               scope="llm", component_id="service:llm",
               default="http://host.docker.internal:11434/v1",
               label="Embedding base URL",
               help="OpenAI-compatible /embeddings endpoint. Ollama default shown."),
    ConfigSpec(key="llm.embedding.model", type="string",
               scope="llm", component_id="service:llm",
               default="mxbai-embed-large",
               label="Embedding model",
               help="Must produce vectors of EMBEDDING_DIM (1024) dimensions."),
    ConfigSpec(key="llm.embedding.api_key_env", type="string",
               scope="llm", component_id="service:llm",
               default=None, label="Embedding API key env var",
               help="Env var holding the API key (leave empty for local servers)."),
]

SPEC_BY_KEY: dict[str, ConfigSpec] = {s.key: s for s in SPECS}


def validate_value(key: str, value: Any) -> tuple[bool, str | None]:
    """Validate a candidate value against its spec. Returns (ok, error_message)."""
    spec = SPEC_BY_KEY.get(key)
    if spec is None:
        return False, f"unknown config key: {key}"
    t = spec.type
    if t == "bool":
        if not isinstance(value, bool):
            return False, "expected a boolean"
    elif t in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, f"expected a {t}"
        if t == "int" and not float(value).is_integer():
            return False, "expected an integer"
        if spec.minimum is not None and value < spec.minimum:
            return False, f"must be >= {spec.minimum}"
        if spec.maximum is not None and value > spec.maximum:
            return False, f"must be <= {spec.maximum}"
    elif t == "string":
        if not isinstance(value, str):
            return False, "expected a string"
    elif t == "enum":
        if value not in (spec.choices or []):
            return False, f"must be one of {spec.choices}"
    elif t == "list":
        if not isinstance(value, list):
            return False, "expected a list"
    elif t == "json":
        if not isinstance(value, (dict, list)):
            return False, "expected an object or array"
    return True, None


def public_value(key: str, value: Any) -> Any:
    """Mask secrets for read responses."""
    spec = SPEC_BY_KEY.get(key)
    return "***" if (spec and spec.secret) else value
