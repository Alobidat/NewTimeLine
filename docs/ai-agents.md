# AI Agent Pipeline (Feed-First, Tiered)

The agents are the engine of Chronos: they continuously discover events, enrich them,
link them across history, and score them — **without** running an expensive LLM on every
item. The guiding principle (your locked decision) is **feed-first**: pull structured
data cheaply, and spend LLM tokens only where they add real value.

## 1. Cost philosophy: three tiers

```
TIER 1 — INGEST (cheap, high volume)        ~$0 LLM
  Structured feeds + rules. No LLM.
  GDELT, news APIs, RSS, govt/agency data, open datasets.
        │ candidate events
        ▼
TIER 2 — ENRICH (selective LLM)             $ controlled
  Runs ONLY on new or materially-changed events.
  Entity extraction, neutral summary, impact signals, tags.
        │ enriched events
        ▼
TIER 3 — DEEP DIG (rare, on-demand)         $$ budgeted
  Triggered for high-severity / high-interest / user-requested events.
  Historical research: trace precursors, build relation graph, multi-source synthesis.
```

A per-day **token budget** caps tiers 2–3. When exceeded, the system degrades gracefully:
new events still appear (from feeds) but wait in a queue for enrichment.

## 2. Pipeline stages

Each stage is an independent worker consuming from / producing to the message queue, so
stages scale and fail independently.

```
[Schedulers] ──► Ingestors ──► Normalizer ──► Deduper ──► Enricher(LLM) ──►
   Geocoder ──► Relation-linker ──► Severity-scorer ──► Publisher ──► (notify/recommend/realtime)
```

### 2.1 Ingestors (Tier 1)
- One adapter per source type. Each polls on its own schedule (live news: minutes;
  datasets: daily/weekly).
- Writes raw items to `ingest_items` (dedup by `(feed, external_id)`) and enqueues them.
- **Source candidates:**
  - *Live/news:* GDELT (global event stream, free), news aggregator APIs, major RSS feeds,
    official agency feeds (USGS earthquakes, weather/disaster alerts, etc.).
  - *Historical:* Wikidata (structured, time-stamped, geocoded, with QIDs), Wikipedia
    "On this day"/event lists, curated open history datasets.
- No LLM here. Pure fetch + structural parse.

### 2.2 Normalizer
- Maps each raw item to a **candidate event**: title, text, time + precision, links, raw
  place strings, raw entity hints.
- Derives `time_precision` from the source (Wikidata gives precision; news ≈ `day`/`exact`).
- Rule-based filtering of junk (ads, duplicates by content hash, non-events).

### 2.3 Deduper (the merge brain)
- Embeds the candidate (embedding model) and queries `events.embedding` for near matches
  within a time/place gate.
- **Fast path (no LLM):** high similarity + same day + same place → merge: attach the new
  source to the existing event, bump corroboration.
- **Ambiguous path (LLM adjudication):** borderline similarity → a small LLM call decides
  "same event / different event / sub-event." This is where the LLM earns its cost.
- Merge updates `event_sources` (more sources = higher corroboration), never silently
  discards information.

### 2.4 Enricher (Tier 2 — the main LLM step)
Runs once per **new or changed** event. A single structured LLM call (forced JSON schema)
extracts:
- `summary` — neutral, concise, source-grounded (no speculation),
- `entities` — people / orgs / places / topics (linked to Wikidata QIDs when possible),
- `impact signals` — scale indicators (casualties, area, economic, displacement) used by
  the severity scorer,
- `category` + `tags`,
- `time` refinement + precision if the feed was vague.
Grounding: the prompt includes the source text(s); the model is instructed to only assert
what sources support and to flag uncertainty. Outputs are validated against a schema.

### 2.5 Geocoder
- Resolves place strings/entities → coordinates/areas (PostGIS `geom`).
- Prefer **structured** geocoding (Wikidata coords, gazetteers) before any geocoding API.
- Stores point for cities/incidents, polygon for regions/areas where known.

### 2.6 Relation-linker (history graph)
- For each event, find related events via:
  - **shared entities** (`event_entities` — same person/org/place),
  - **embedding similarity** (thematic neighbors),
  - **geo + time proximity** (PostGIS + temporal window),
  - **causal/precursor** hints from the enricher.
- Writes `event_relations` with `kind` + `weight`. This powers "see related/historical
  events" navigation and the contextual digging the product promises.
- Heavy causal/historical synthesis is deferred to Tier 3 for important events only.

### 2.7 Severity-scorer {#severity}
Composite 0–100, recomputed when inputs change:

```
severity = clamp(
    w_impact        * impact_norm        +   # from enricher impact signals
    w_social        * social_norm        +   # likes/comments/follows velocity
    w_corroboration * corroboration_norm     # # distinct quality-weighted sources
, 0, 100)

# default weights (tunable via config):
w_impact = 0.5,  w_social = 0.2,  w_corroboration = 0.3
```
- `impact_norm`: normalized scale from extracted signals (log-scaled casualties/area/$).
- `social_norm`: time-decayed engagement velocity (prevents stale events dominating).
- `corroboration_norm`: distinct sources weighted by `sources.quality_score`, saturating.
- `severity_breakdown` is stored so the UI can explain "why is this red?" and so weights
  can be re-tuned transparently.
- A separate `confidence` score (source corroboration + community validation) is tracked
  apart from severity — a low-confidence event can still be high-severity-if-true and is
  badged accordingly.

### 2.8 Publisher
- Writes/updates the canonical `events` row, sets `status='published'`.
- Invalidates/updates affected **timeline buckets** in Redis (incremental).
- Emits a `event.published` / `event.updated` message → notification, recommendation, and
  real-time gateways.

## 3. Tier 3 — Deep historical dig (on-demand, budgeted)
Triggered when an event crosses a severity/interest threshold, or a user explicitly asks
"dig into the history of this."
- Multi-step agent: gather more sources, trace precursors and consequences, synthesize a
  longer narrative (`events.body`), strengthen the relation graph, propose new linked
  historical events that may not yet be in the DB (which then re-enter at the Normalizer).
- This is where a **workflow-style orchestration** (fan-out research → verify → synthesize)
  fits. Strictly budget-capped and rate-limited.

## 4. Orchestration & scheduling
- A scheduler triggers ingestors on cron-like intervals per feed.
- Stages communicate via the queue; each is idempotent and retry-safe (keyed by
  `ingest_items.id` / `events.id`).
- Backpressure: if enrichment falls behind, ingestion continues (events queue for Tier 2);
  dashboards alert on lag.
- **Idempotency & replay:** `ingest_items` retains raw input so the whole pipeline can be
  replayed after a logic change without re-fetching feeds.

## 5. Quality, safety, neutrality
- **Grounding:** enrichment asserts only what sources support; speculation is flagged.
- **Bias/neutrality:** summaries are instructed to be neutral; multiple sources of
  differing perspective are preferred; the UI always shows sources so users can judge.
- **Misinformation resistance:** corroboration + community validation + source quality
  gate `confidence`; single-source low-quality events are badged as unverified.
- **Hallucination guard:** schema-validated outputs; entities cross-checked against
  Wikidata where possible; dedup prevents fabricated duplicates.
- **Cost guardrails:** per-day token budget; degrade to feed-only when exceeded; cache
  enrichment by `content_hash` to avoid re-paying for identical inputs.

## 6. Cost levers summary
| Lever | Effect |
|-------|--------|
| Feed-first ingestion (Tier 1) | Bulk of events arrive with $0 LLM |
| Enrich only new/changed events | Avoids re-paying per source |
| Structured geocoding before API geocoding | Cuts geocoding spend |
| LLM dedup only on ambiguous cases | Most merges are free (vector + rules) |
| Tier-3 gated by severity/interest | Expensive research only where it matters |
| Daily token budget + cache | Hard ceiling on spend |

## 7. Which LLM
Use **Claude** via API, sized per task:
- **Dedup adjudication, enrichment:** a fast/cheaper Claude tier (e.g. latest Sonnet/Haiku
  class) — high volume, structured output.
- **Tier-3 deep dig / synthesis:** a stronger Claude tier (e.g. latest Opus/Sonnet class)
  — low volume, high value.
Model selection is config-driven so tiers can be re-balanced as pricing/quality change.
