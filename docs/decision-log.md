# Decision Log (ADR-style)

Chronological, append-only record of decisions so we **never start from scratch**. Each
entry is short. When we change our mind, we add a *new* entry that supersedes the old one
(don't edit history). [decisions.md](decisions.md) holds the high-level summary table; this
file holds the running log with context.

Format: `ADR-NNNN — Title` · *date* · status · the decision · why.

---

### ADR-0001 — First deliverable is architecture + plan
*2026-06-18* · accepted
Produce architecture/design docs before any app code. Why: large system; validate
direction cheaply before investing build effort.

### ADR-0002 — Flutter for all clients
*2026-06-18* · accepted
One Dart codebase → Android, iOS, Windows, macOS, Web (and Flutter Web for the admin
portal). Why: single codebase across all required platforms; strong custom-graphics story
for the timeline; keeps us on one UI stack.

### ADR-0003 — Feed-first tiered AI pipeline
*2026-06-18* · accepted
Tier 1 structured feeds (no LLM) → Tier 2 selective LLM enrich/dedup → Tier 3 budgeted
deep dig. Why: cost control; most events arrive with $0 LLM; tokens spent only where they
add value. Detail in [ai-agents.md](ai-agents.md).

### ADR-0004 — Cloud-agnostic, containerized
*2026-06-18* · accepted
Talk to standard interfaces (Postgres, S3-API, AMQP, OIDC); package with Docker; pick the
host at deploy time. Why: portability; avoid lock-in. (Host for testing: on-site Proxmox
LXC — see ADR-0010 / [infrastructure.md](infrastructure.md).)

### ADR-0005 — Dual-time model (anchor time + subject time / sub-timeline)
*2026-06-18* · accepted
Main timeline is **source-bounded**; each event sits at its **anchor time**. Deep-history
periods an event merely *discusses* are stored as `event_references` (subject time) and
render as a **sub-timeline** on open (recursively). Why: keeps the main timeline honest
while letting users dive into the history an event references. Detail in
[data-model.md §1.0](data-model.md).

### ADR-0006 — Admin portal + DB-backed Config Service
*2026-06-18* · accepted
All agent behavior, budgets, capabilities, feeds, and thresholds are runtime config
(versioned, audited, hot-reloaded); an RBAC admin portal configures + monitors them. Why:
operate and tune the system (esp. cost) without redeploys. Detail in
[admin-portal.md](admin-portal.md).

### ADR-0007 — Anonymous browse, social-login interaction
*2026-06-18* · accepted
Anyone can view/search without an account; interaction (react/comment/validate/follow)
requires sign-in via social login (Google/Facebook/Apple…) through OIDC, with first-login
auto-provisioning and multi-provider account linkage. Apple sign-in is included on iOS
(App Store guideline 4.8). Why: low-friction onboarding; broad reach. Detail in
[architecture.md §4.7](architecture.md).

### ADR-0008 — Backend in Python/FastAPI; Postgres+PostGIS+pgvector; Redis; RabbitMQ; S3
*2026-06-18* · accepted
API + agents share Python (Pydantic models reused across both). Postgres+PostGIS for
relational+geo+temporal; pgvector for embeddings (start in Postgres, split out only if
scale demands); Redis cache; RabbitMQ queue; S3-compatible object store (MinIO locally).
Why: one language for the data/AI-heavy work; fewest moving parts that still scale.

### ADR-0009 — Engineering standards: token-economy-first, small files, documented modules
*2026-06-18* · accepted
Adopt [engineering-standards.md](engineering-standards.md) for all phases: clean code,
small single-responsibility files (~300-line soft cap), modules with clear scope and a
README each, public interfaces documented, decisions logged here. Why (the prime
directive): make the codebase cheap for future AI/human sessions to understand and modify
— minimize tokens spent re-reading code.

### ADR-0010 — Host testing on on-site Proxmox LXC
*2026-06-18* · accepted
Use the on-site Proxmox cluster to provision LXC containers for local + public testing
environments. Why: existing on-prem capacity; full control; cost. Topology + open items in
[infrastructure.md](infrastructure.md).

### ADR-0011 — Repository
*2026-06-18* · accepted
Code lives at https://github.com/Alobidat/NewTimeLine (public). Monorepo. Conventional
Commits, PRs into `main`, CI gates. Secrets never committed (`.env`, gitignored).

### ADR-0012 — Canonical time axis is a signed numeric year, not timestamptz
*2026-06-18* · accepted · supersedes the timestamptz anchor in ADR-0005's first draft
The sortable/queryable time of every event and subject reference is a **signed numeric
year** (`t_start`/`t_end`, double precision): e.g. `2011.19` (≈Mar 2011), `-1273` (1274 BC),
`-4000000` (≈4 Mya). Why: Python `datetime` can't represent years < 1 (BC), and PostgreSQL
`timestamptz` bottoms out at 4713 BC — but the sub-timeline must reach **millions of years**
(ADR-0005's "origin of life" example). A numeric year spans all of time uniformly and is
trivially indexable/bucketable. We additionally keep an **optional `instant timestamptz`**
on events for precise modern times (exact display + intra-day ordering). `t_end` is
**materialized at write time** from `event_end` or the precision window, so timeline-overlap
queries are a simple indexable range test. Detail in [data-model.md §1](data-model.md).

### ADR-0013 — Client map uses flutter_map (not native maplibre_gl)
*2026-06-18* · accepted · refines ADR-0002's "MapLibre GL" intent for the client
The Flutter client renders the map with **flutter_map** (pure-Dart) rather than the native
`maplibre_gl` plugin. Why: flutter_map builds and runs uniformly across web + Windows +
mobile with no native toolchain setup, keeping the cross-platform build simple and
CI-verifiable; it consumes standard raster/vector tile URLs (incl. MapLibre/OSM tiles), so
the architecture's MapLibre-tile intent is preserved. We can swap in vector-tile/native
MapLibre later for richer rendering without changing the data flow. Phase 2b uses OSM raster
tiles for the dev/test stage; pick a tile provider/self-host for production.

### ADR-0014 — Pluggable, provider-agnostic LLM layer (cloud + local)
*2026-06-18* · accepted
Agents talk to LLMs through a common `LLMProvider` interface with two implementations: an
**Anthropic** provider (Claude) and an **OpenAI-compatible** provider that serves **vLLM,
Ollama, and OpenAI** (all expose `/v1/chat/completions`). Providers, models, endpoints, and
which is primary/fallback are all defined in the Config Service (`llm.providers`,
`llm.routing`) — no code change to add or switch a provider. Why: the user requires support
for any LLM provider including locally-hosted ones; a thin interface keeps the agents
provider-agnostic. Detail in [ai-agents.md](ai-agents.md).

### ADR-0015 — Budget-aware LLM routing with auto-fallback to local
*2026-06-18* · accepted
An `LLMRouter` picks the provider per call: it uses the primary unless the primary is a
**cloud** provider AND the **token budget for the current time window is spent**, in which
case it switches to the **local** fallback. Budget (`llm.budget.max_tokens`,
`window_seconds`) is configurable and tracked in Redis (only cloud tokens count). On a
primary error it also falls back. Default routing for this project: **primary = local
Ollama** (no cost, no budget pressure), with cloud as an optional quality tier. Why: the
user wants automatic switch to a local LLM once the budgeted cloud tokens are used in a time
frame — fully configurable. Detail in [ai-agents.md](ai-agents.md) + [admin-portal.md](admin-portal.md).

### ADR-0016 — The product's core is an entity-anchored causal graph, not a geo-feed
*2026-06-19* · accepted
NewTimeLine is about **digging back-and-forth through linked events**, not plotting a live
feed of disparate incidents (earthquakes etc.). The user journey: search a **location /
actor / title / date** → land on a few anchor events → traverse **what led to** them and
**what they caused**, anchored on one or a few key places/actors (the worked example: the
"US ↔ Iran" relationship, with Gulf states as secondary links). Decisions:
- **Entities (`entities` + `event_entities`)** are first-class anchors; the enricher tags
  the primary countries/actors (role `actor`) and where it happened (role `location`).
- **`event_relations`** is a **directed** graph, convention **src = earlier/cause → dst =
  later/effect**. "Led to" = edges into an event; "caused" = edges out.
- A cheap **Tier-1 relation-linker** builds the structural backbone from **shared entities**
  + time order (`same-place`, `same-actor`, and a `precursor` candidate-causal edge); heavy
  causal adjudication stays in the Tier-3 dig. Why no embeddings yet: the vision is anchored
  on *who/where*, not thematic similarity — shared entities are the right, cheap signal.
- New API: `/search`, `/entities`, `/events/by-entities` (intersection = "all events linking
  the US and Iran"), `/events/{id}/related` (one-hop), and `/events/{id}/chain` (recursive
  back/forth walk over causal kinds). Detail in [data-model.md](data-model.md) §3.3–3.4 +
  [ai-agents.md](ai-agents.md) §2.6.

### ADR-0017 — Rich media: store locally in the object store, link many-to-many, accept later links
*2026-06-19* · accepted
Event detail must carry **images and video clips**, stored **locally** (the existing
S3-compatible MinIO/object store, ADR-0008) and linked flexibly. Decisions:
- **`media`** row per asset: binaries live in the object store (`storage_key` +
  `thumbnail_key`); large/owned video may instead be referenced as an external player
  (`embed_url`, status `external`) to avoid storage/copyright cost. `content_hash` dedups
  identical binaries.
- **`event_media`** is a **link table** (not a column on `events`) so one asset can attach
  to several related events, with a `role` (hero/gallery/inline/related) + `rank`. `added_by`
  records provenance — an **agent run OR a user id** — so links may be added **later by users
  or by a new source**, exactly the extensibility the user asked for.
- **Gathering (planned, built next pass):** Tier-1 ingestors capture media URLs (RSS
  enclosures, `og:image`, `media:content`, oEmbed); a **media-fetcher** worker downloads,
  dedups by hash, stores the binary + a generated thumbnail to the object store, and writes
  `media` + `event_media`. Video defaults to **thumbnail + embed reference**; full download
  only when license permits. Serving uses **signed/proxied URLs** from the API (deferred).
  Why store the schema + link model now: it ships with migration 0002 so no later migration
  is needed, and the detail API already returns `media` the moment rows exist.

### ADR-0018 — Media archival: capture-first by risk, release-when-durable
*2026-06-19* · accepted
Media on hot/sensitive events **disappears** from its origin under political, government, or
social pressure. The system must decide, per media item and **re-evaluate over time**,
whether to keep a local copy. Decision (pure engine `chronos_core.domain.media_policy`, fed
by rule-based signals — no LLM):
- **Disposition = `pin | archive | link`.** `pin` = store locally and **never auto-release**
  (high `sensitivity`: external availability is never sufficient confidence because pressure
  can take down *all* copies). `archive` = store now, release later **iff** proven durable.
  `link` = reference only (low sensitivity + durable, corroborated host).
- **Signals:** `sensitivity` (0–100, from event category/tags + `social`/user origin),
  origin **ephemerality** (social/ephemeral domains vs. Wikimedia/archive.org/primary-doc),
  **corroboration** (independent stable hosts via `media_sources`), and **time-survived**
  → a `persistence_confidence` (0–100).
- **Archive-first default:** an ambiguous item is stored locally (we never lose it for want
  of a signal); storage is reclaimed later only once `persistence_confidence` clears the
  release threshold AND it isn't sensitive.
- **Sensitivity detection: rules now, LLM later** (the enricher may add a sensitivity flag in
  a later pass). The **checker** re-evaluates sensitivity from the (now-enriched) citing
  events and can **upgrade to `pin`**, **escalate** a vanished link to a capture attempt, or
  **release** a durable copy.
- **Two Tier-1 workers:** `media-fetch` (download → object store, dedup by content hash,
  over-large binaries stay linked) and `media-check` (re-probe hosts, recompute confidence,
  apply retention). Storage = the existing S3/MinIO object store (ADR-0008); serving via
  signed URLs is deferred. Schema: migration 0003 (`media` policy columns + `media_sources`).
