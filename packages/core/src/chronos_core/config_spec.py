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

# Auth providers (ADR-0026): the non-secret half of the provider registry. Each entry is a
# toggle + client_id + scopes; the matching client SECRET lives in Settings (env). A provider
# is only offered to clients when ``enabled`` AND it has a client_id (config) AND a secret
# (env). Default ships them DISABLED with empty client_ids so the app boots with no providers
# configured → /auth/providers returns []. Adding a provider is config, not code.
_AUTH_PROVIDERS = [
    {"id": "google", "enabled": False, "client_id": "",
     "scopes": ["openid", "email", "profile"]},
    {"id": "apple", "enabled": False, "client_id": "",
     "scopes": ["name", "email"]},
    {"id": "facebook", "enabled": False, "client_id": "",
     "scopes": ["email", "public_profile"]},
    {"id": "twitter", "enabled": False, "client_id": "",
     "scopes": ["users.read", "tweet.read"]},
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


def _e(key, default, label, choices, *, scope, component_id, help=""):
    return ConfigSpec(key=key, type="enum", scope=scope, default=default, label=label,
                      help=help, component_id=component_id, choices=choices)


_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


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
    # Pipeline maintenance heartbeat (worker): periodically enqueues enrich/geocode/dedup/relate
    # so new + backlogged events stay processed without manual runs.
    _b("agents.maintenance.enabled", True, "Pipeline maintenance heartbeat",
       scope="agent:enrich", component_id="agent:enrich",
       help="When on, the worker periodically runs enrich → geocode → dedup → relate so new "
            "events get summarized, placed on the map, embedded/deduped, and graph-linked."),
    _i("agents.maintenance.interval_seconds", 900, "Maintenance interval (seconds)",
       scope="agent:enrich", component_id="agent:enrich", minimum=60, maximum=86400,
       help="How often the worker enqueues the maintenance pipeline."),

    # LLM moderation (Phase 6) — reviews user posts/comments; flags + optionally holds.
    _b("moderation.enabled", True, "Enabled", scope="agent:moderation",
       component_id="agent:moderation",
       help="Run the async LLM moderation pass over user posts + comments."),
    _i("moderation.hold_threshold", 90, "Auto-hold severity (0-100)",
       scope="agent:moderation", component_id="agent:moderation", minimum=0, maximum=100,
       help="Flagged content is *held* (event→pending, comment→flagged) only at or above this "
            "severity; below it the post stays live with an open flag for the admin queue."),
    _i("moderation.max_tokens", 200, "Max tokens / call",
       scope="agent:moderation", component_id="agent:moderation", minimum=32, maximum=2048),

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

    # Media quality (clips > images > text, ADR-0024). Tunes what collectors fetch + attach.
    _b("agents.media.prefer_clips", True, "Prefer clips as hero",
       scope="agent:media", component_id="agent:collect",
       help="Rank a video clip ahead of images so the event hero is a clip when one exists."),
    _i("agents.media.min_image_width", 640, "Min hero image width (px)",
       scope="agent:media", component_id="agent:collect", minimum=0, maximum=4096,
       help="The hero resolution floor (ADR-0024): an image may only be an event's hero when "
            "its width is MEASURED and at least this. Unmeasured images are measured at publish "
            "time; below-floor or unmeasurable images are kept as gallery, never hero."),
    _i("agents.media.min_clip_width", 240, "Min hero clip width (px)",
       scope="agent:media", component_id="agent:collect", minimum=0, maximum=3840,
       help="A clip with a known width below this is too low-res to be the hero."),
    _i("agents.media.max_clip_width", 720, "Max clip width (px)",
       scope="agent:media", component_id="agent:collect", minimum=120, maximum=3840,
       help="Largest browser-playable WebM rendition to fetch — higher = better quality, "
            "heavier. Source adapters pick the biggest clip up to this width."),

    # Deduper (pgvector cosine similarity, Phase 3b)
    # Smart causal linker (Tier-2 LLM) — the back-and-forth history chain.
    _b("agents.relate_smart.enabled", True, "Enabled",
       scope="agent:relate.smart", component_id="agent:relate.smart"),
    _i("agents.relate_smart.batch_size", 8, "Anchors / run",
       scope="agent:relate.smart", component_id="agent:relate.smart", minimum=1, maximum=100,
       help="Un-processed events to LLM-link per run (one LLM call each)."),
    _i("agents.relate_smart.candidates", 10, "Candidates / anchor",
       scope="agent:relate.smart", component_id="agent:relate.smart", minimum=2, maximum=40,
       help="Embedding-similar events offered to the LLM to judge per anchor."),
    ConfigSpec(key="agents.relate_smart.min_similarity", type="float",
               scope="agent:relate.smart", component_id="agent:relate.smart",
               default=0.45, label="Min cosine similarity", minimum=0.0, maximum=1.0,
               help="Candidate floor: only embedding neighbours at/above this similarity."),
    _i("agents.relate_smart.confidence_threshold", 70, "Confidence threshold",
       scope="agent:relate.smart", component_id="agent:relate.smart", minimum=0, maximum=100,
       help="Only keep links the LLM is at least this confident are real."),
    _i("agents.relate_smart.max_tokens", 700, "Max tokens / call",
       scope="agent:relate.smart", component_id="agent:relate.smart", minimum=128, maximum=4096),

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

    # On-demand collection agent (event-presentation.md §5.2 / §6)
    _b("agents.collect.enabled", True, "Enabled",
       scope="agent:collect", component_id="agent:collect",
       help="On-demand collection from all enabled source adapters for a searched subject."),
    _i("agents.collect.max_per_adapter", 10, "Max events / adapter",
       scope="agent:collect", component_id="agent:collect", minimum=1, maximum=100,
       help="Per-adapter cap on candidates fetched per collection run."),

    # Source adapters (per-adapter on/off; the collector queries all that are enabled)
    _b("agents.sources.wikipedia.enabled", True, "Wikipedia source",
       scope="agent:collect", component_id="agent:collect",
       help="Full-text Wikipedia search with lead image + WebM clip (media-rich, clips-first)."),
    _b("agents.sources.wikidata.enabled", True, "Wikidata source",
       scope="agent:collect", component_id="agent:collect",
       help="Dated, geolocated SPARQL events filtered by the subject label."),
    _b("agents.sources.rss.enabled", True, "RSS source",
       scope="agent:collect", component_id="agent:collect",
       help="Subject-matched entries from the configured RSS feed set."),

    # Media-gap agent (no-text-only / clips-first enforcement, ADR-0023)
    _b("agents.media.gap.enabled", True, "Gap enabled",
       scope="agent:media", component_id="agent:media.gap",
       help="Re-collect media for published events that have no image (text-only)."),
    _i("agents.media.gap.batch_size", 20, "Gap batch size",
       scope="agent:media", component_id="agent:media.gap", minimum=1, maximum=200),

    # Faceted search + live collection (event-presentation.md §5 / ADR-0022).
    # Owned by the API surface (no component manifest), so component_id stays None.
    _b("search.live_collection.enabled", True, "Search triggers live collection",
       scope="search", component_id=None,
       help="Each /search enqueues a 'collect' job onto the Redis run-queue so the corpus "
            "expands on demand (ADR-0022). Disable to make search read-only."),
    _i("search.facet_limit", 10, "Facet result limit",
       scope="search", component_id=None, minimum=1, maximum=50,
       help="Max actors and max places returned per faceted /search response."),
    _i("search.stream.poll_seconds", 3, "Search stream poll interval (s)",
       scope="search", component_id=None, minimum=1, maximum=30,
       help="How often the /search/stream SSE endpoint polls for newly-collected matches."),
    _i("search.stream.max_seconds", 120, "Search stream lifetime (s)",
       scope="search", component_id=None, minimum=5, maximum=900,
       help="Upper bound on a single /search/stream connection before the client reconnects."),

    # Accounts / auth (ADR-0026). Non-secret toggles; client secrets live in Settings (env).
    # Owned by the API auth surface (no component manifest) → component_id None.
    ConfigSpec(key="auth.providers", type="json", scope="auth", default=_AUTH_PROVIDERS,
               label="Auth providers", component_id=None,
               help="Social-login providers (enabled + client_id + scopes). The client "
                    "SECRET is set via env/Settings. A provider is offered only when enabled "
                    "AND has a client_id AND a secret. Empty/disabled → /auth/providers is []."),
    ConfigSpec(key="auth.redirect_base", type="string", scope="auth", default="",
               label="OAuth redirect base URL", component_id=None,
               help="Public base URL the provider redirects back to; the callback path "
                    "/auth/{provider}/callback is appended. Empty → derived from the request."),
    ConfigSpec(key="auth.agreement_version", type="string", scope="auth", default="2026-06-21",
               label="Agreement version", component_id=None,
               help="Current Terms/acceptable-use/privacy version. Bumping it re-prompts every "
                    "user; interaction requires an acceptance of this exact version."),
    ConfigSpec(key="auth.agreement_url", type="string", scope="auth",
               default="https://newtimeline.app/legal/terms",
               label="Agreement document URL", component_id=None,
               help="Where the current agreement text is published (shown to the user)."),
    _b("auth.require_email_verified", True, "Require verified email to interact",
       scope="auth", component_id=None,
       help="Gate writes on a verified email (ADR-0026). Providers asserting a verified "
            "email satisfy it; otherwise the user verifies via emailed code."),
    _b("auth.dev_login_enabled", True, "Enable dev email-code login",
       scope="auth", component_id=None,
       help="Offer a self-contained email + emailed-code sign-in (no external OAuth "
            "provider). Provisions/links a verified user from the email. Intended for "
            "pre-launch testing — DISABLE in production once social login is configured."),

    # Feed / recommendations (ADR-0028, social-and-feed §4-5). Owned by the API feed surface
    # (no component manifest) → component_id None.
    _i("feed.page_size", 10, "Feed page size",
       scope="feed", component_id=None, minimum=1, maximum=50,
       help="Events per /feed/{tab} page (the swipe feed preloads neighbours)."),
    ConfigSpec(key="rec.foryou_weights", type="json", scope="feed", component_id=None,
               default={"recency": 1.0, "popularity": 0.6, "media": 0.8,
                        "interest": 1.2, "seen": 2.0},
               label="For-You blend weights",
               help="Term weights for the For-You score: recency + popularity (votes/views) "
                    "+ media-richness (clips first) + interest-match − already-seen (ADR-0028)."),
    ConfigSpec(key="rec.decay_half_life_days", type="float", scope="feed", component_id=None,
               default=14.0, label="Interest decay half-life (days)",
               minimum=0.5, maximum=365.0,
               help="Age at which an activity's contribution to the interest profile halves."),

    # Upload (ADR-0029). Owned by the API upload surface → component_id None.
    _i("upload.max_bytes", 209_715_200, "Max upload size (bytes)",
       scope="upload", component_id=None, minimum=1_000_000, maximum=2_147_483_647,
       help="Largest user video accepted by POST /upload (default 200 MB)."),
    ConfigSpec(key="upload.allowed_mime", type="list", scope="upload", component_id=None,
               default=["video/mp4", "video/webm", "video/quicktime", "video/ogg"],
               label="Allowed upload MIME types",
               help="Content types accepted by POST /upload; others are rejected (415)."),

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

    # ── AI users (bot personas) ──────────────────────────────────────────────────────────
    # Global switches (kill-switch + per-activity gates honoured by every bot engine).
    _b("bots.enabled", True, "Bots enabled (global)",
       scope="bots", component_id="agent:bots.scheduler",
       help="Master switch: when off, no bot posts or interacts."),
    _b("bots.posts_enabled", True, "Posting enabled",
       scope="bots", component_id="agent:bots.post"),
    _b("bots.interacts_enabled", True, "Interaction enabled",
       scope="bots", component_id="agent:bots.interact"),
    _i("bots.max_concurrent", 5, "Max jobs per scheduler tick",
       scope="bots", component_id="agent:bots.scheduler", minimum=1, maximum=64,
       help="Upper bound on post/interact jobs the scheduler enqueues per tick."),
    _i("bots.tick_interval_seconds", 600, "Scheduler tick interval (seconds)",
       scope="bots", component_id="agent:bots.scheduler", minimum=30, maximum=86400,
       help="How often the worker runs the bot scheduler tick (the feed's heartbeat)."),
    _i("bots.global_quality_floor", 50, "Global quality floor",
       scope="bots", component_id="agent:bots.post", minimum=0, maximum=100,
       help="A clip must score at least this (and the bot's own threshold) to be posted."),
    _i("bots.default_post_cadence_min", 720, "Default post cadence (min)",
       scope="bots", component_id="agent:bots.scheduler", minimum=1, maximum=100000),
    _i("bots.default_interact_cadence_min", 180, "Default interact cadence (min)",
       scope="bots", component_id="agent:bots.scheduler", minimum=1, maximum=100000),
    _i("bots.daily_post_cap", 3, "Global daily post cap",
       scope="bots", component_id="agent:bots.post", minimum=0, maximum=1000),
    _i("bots.daily_interact_cap", 30, "Global daily interact cap",
       scope="bots", component_id="agent:bots.interact", minimum=0, maximum=10000),
    _i("bots.post.candidates", 6, "Candidate clips per post",
       scope="bots", component_id="agent:bots.post", minimum=1, maximum=50,
       help="How many discovered clips to consider (LLM picks the first that clears the bar)."),
    _i("bots.interact.events_per_run", 5, "Events per interact run",
       scope="bots", component_id="agent:bots.interact", minimum=1, maximum=50),
    _b("bots.allow_noncommercial", False, "Allow non-commercial (NC) licenses",
       scope="bots", component_id="agent:bots.post",
       help="When off, CC BY-NC clips are rejected (commercial-safe). Default off."),
    _i("bots.persona_gen.batch_size", 20, "Persona generation batch size",
       scope="bots", component_id="agent:persona.gen", minimum=1, maximum=100),

    # Free-video providers (each license-gated). youtube_cc ships DISABLED (ToS caveat).
    _b("bots.sources.commons.enabled", True, "Wikimedia Commons",
       scope="bots", component_id="agent:bots.post"),
    _b("bots.sources.nasa.enabled", True, "NASA (public domain)",
       scope="bots", component_id="agent:bots.post"),
    _b("bots.sources.archive.enabled", True, "Internet Archive (keyless, free-license movies)",
       scope="bots", component_id="agent:bots.post",
       help="Public-domain / CC0 / CC-BY / CC-BY-SA movies; deep archival breadth, no key."),
    _b("bots.sources.pexels.enabled", True, "Pexels (needs API key)",
       scope="bots", component_id="agent:bots.post"),
    ConfigSpec(key="bots.sources.pexels.api_key", type="string", scope="bots",
               component_id="agent:bots.post", default="", label="Pexels API key",
               secret=True, help="Enables Pexels stock-video + portrait avatars."),
    _b("bots.sources.pixabay.enabled", True, "Pixabay (needs API key)",
       scope="bots", component_id="agent:bots.post"),
    ConfigSpec(key="bots.sources.pixabay.api_key", type="string", scope="bots",
               component_id="agent:bots.post", default="", label="Pixabay API key",
               secret=True, help="Enables the Pixabay free-stock video provider."),

    # ── System health / monitoring (the collector ticker in the worker) ───────────────────
    _b("monitoring.enabled", True, "Health monitor enabled",
       scope="monitoring", component_id="agent:monitor",
       help="When on, the worker periodically probes every component and samples "
            "container/host resource utilization (CPU/mem/net/disk)."),
    _i("monitoring.collector.interval_seconds", 30, "Collector interval (seconds)",
       scope="monitoring", component_id="agent:monitor", minimum=5, maximum=3600,
       help="How often the monitor probes components and records resource samples."),
    _i("monitoring.metric_retention_days", 14, "Metric retention (days)",
       scope="monitoring", component_id="agent:monitor", minimum=1, maximum=365,
       help="Resource samples older than this are pruned each collector cycle."),
    _i("monitoring.log_retention_days", 7, "Log retention (days)",
       scope="monitoring", component_id="agent:monitor", minimum=1, maximum=90,
       help="Persisted WARNING+ log records older than this are pruned."),
    _i("monitoring.log_buffer_max_rows", 50_000, "Log buffer max rows",
       scope="monitoring", component_id="agent:monitor", minimum=1_000, maximum=1_000_000,
       help="Ceiling on the persisted log ring buffer; oldest rows are trimmed past this."),
    ConfigSpec(key="monitoring.thresholds", type="json", scope="monitoring",
               component_id="agent:monitor",
               default={
                   "host.disk_used_pct": {"warning": 80, "critical": 92},
                   "*.cpu_pct": {"warning": 85, "critical": 96},
                   "store:postgres.connections": {"warning": 80, "critical": 95},
                   "agent:media.quality.low_quality_pending": {"warning": 20, "critical": 100},
               },
               label="Degradation thresholds",
               help="metric → {warning, critical} cut-offs the collector uses to set each "
                    "component's level. Keys are '<component_id>.<metric>' or '*.<metric>'. "
                    "Consumed in Phase C; safe to edit now."),

    # ── Logging (centralized init + runtime per-process level control) ────────────────────
    _e("logging.default.level", "INFO", "Default log level", _LOG_LEVELS,
       scope="logging", component_id=None,
       help="Fallback log level for any process without an explicit override below."),
    _e("logging.api.level", "INFO", "API log level", _LOG_LEVELS,
       scope="logging", component_id="service:api",
       help="Runtime root log level for the API process (picked up within a refresh cycle)."),
    _e("logging.worker.level", "INFO", "Worker log level", _LOG_LEVELS,
       scope="logging", component_id="service:worker",
       help="Runtime root log level for the worker process (picked up within a cycle)."),
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
