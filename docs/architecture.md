# Architecture

This document describes the end-to-end system architecture for Chronos (NewTimeLine):
a globally-scoped, AI-fed, social event timeline.

## 1. Design goals & constraints

| Goal | Implication |
|------|-------------|
| Cross-platform (Android, iOS, PC, web) from one codebase | **Flutter** client |
| Rich, animated timeline + interactive globe/map | GPU-accelerated custom rendering; server pre-aggregates timeline buckets |
| Events span **all of history** (ancient → live) | Temporal model with variable precision (see data-model.md) |
| Continuous background event discovery, cost-controlled | **Feed-first tiered** agent pipeline; LLM used sparingly |
| Community discussion + source validation | Social graph, comments, source-vote/reputation system |
| Notify subscribers; recommend to similar users | Subscription model + recommendation service + push/real-time |
| **Browse/search without an account; interact only when signed in** | Public read APIs; **social login** (Google/Facebook/Apple…) via OIDC; auth-gated writes |
| **Everything the agents do/spend is configurable & monitored** | **Admin portal + Config Service** (DB-backed, hot-reloaded, audited) |
| Cloud-agnostic for v1 | Containerized services, standard interfaces (S3-API, Postgres, AMQP/queue) |

### Non-goals for v1
- Real-time chat / DMs (timeline + threaded comments only).
- Video hosting (link out / thumbnails only; object store holds source snapshots, not user video).
- On-device ML.

## 2. High-level component map

```
┌────────────────────────────────────────────┐   ┌────────────────────────┐
│              FLUTTER CLIENTS                  │   │   ADMIN PORTAL          │
│  Timeline · Globe/Map · Event detail (+sub-  │   │  (Flutter Web)          │
│  timeline) · Sources · Social                │   │  agents · budgets ·     │
│  Anonymous: view/search · Signed-in: interact│   │  feeds · moderation ·   │
│  (Android · iOS · Windows · macOS · Web)     │   │  dashboards             │
└───────────────┬──────────────────────┬───────┘   └───────────┬────────────┘
                │ HTTPS REST + WebSocket │                       │ Admin API (RBAC, audited)
                ▼                        ▼                       ▼
┌──────────────────────────────┐   ┌──────────────────────────────────┐
│        API GATEWAY            │   │      REAL-TIME GATEWAY            │
│  Auth (OIDC/social login),    │   │  WebSocket / SSE: live events,   │
│  rate limit, routing;         │   │  notifications, comment streams  │
│  public reads / gated writes  │   │                                  │
└───────────────┬──────────────┘   └───────────────┬──────────────────┘
                │                                    │
   ┌────────────┼─────────────┬──────────────┬──────┴───────┐
   ▼            ▼             ▼              ▼              ▼
┌──────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐
│Event │  │ Social   │  │ Search/  │  │ Notif.   │  │ User/Auth/   │
│ API  │  │ API      │  │ Recommend│  │ Service  │  │ Profile      │
│      │  │(likes,   │  │ Service  │  │(fan-out, │  │              │
│      │  │ comments,│  │(semantic+│  │ push)    │  │              │
│      │  │ votes)   │  │ filters) │  │          │  │              │
└──┬───┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘
   │           │             │             │               │
   └───────────┴─────────────┴─────────────┴───────────────┘
                          │ shared data layer
   ┌──────────────────────┼───────────────────────────────────┐
   ▼              ▼                ▼               ▼            ▼
┌────────┐  ┌──────────┐   ┌────────────┐  ┌──────────┐  ┌─────────┐
│Postgres│  │ Vector   │   │ Object     │  │ Cache    │  │ Message │
│+PostGIS│  │ DB       │   │ Store      │  │ (Redis)  │  │ Queue   │
│(canon. │  │(semantic │   │(source     │  │ sessions,│  │(agent   │
│ data)  │  │ search,  │   │ snapshots, │  │ hot      │  │ jobs,   │
│        │  │ dedup)   │   │ media)     │  │ timeline)│  │ events) │
└────────┘  └──────────┘   └────────────┘  └──────────┘  └────┬────┘
                                                               │ consumes/produces
   ┌───────────────────────────────────────────────────────────┘
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    AI AGENT PIPELINE (background workers)               │
│  Ingestors → Normalizer → Deduper → Enricher(LLM) → Geocoder →        │
│  Relation-linker → Severity-scorer → Publisher                         │
│  Orchestrated by a scheduler; see ai-agents.md                         │
└──────────────────────────────────────────────────────────────────────┘
                ▲                              ▲
                │                              │
        News/Event feeds              Historical datasets
   (GDELT, news APIs, RSS,        (Wikidata, Wikipedia,
    govt/agency data)             curated open datasets)
```

## 3. Recommended tech stack

The stack is chosen to be cloud-agnostic and to keep the data/AI work in one language
while giving the client maximum rendering power.

| Layer | Recommendation | Why |
|-------|----------------|-----|
| **Client** | **Flutter (Dart)** | One codebase → all targets; `CustomPainter`/Impeller for the bespoke timeline; `flutter_map`/MapLibre for maps; strong animation. |
| **Maps** | **MapLibre GL** (open, self-hostable tiles) | Avoids per-render vendor lock-in/cost; vector tiles; works on all Flutter targets. |
| **API services** | **Python + FastAPI** | Same language as the agent/data pipeline; async; great for JSON + ML adjacency. (Alt: Go for the hot read paths if needed later.) |
| **Agent pipeline** | **Python** (workers) + a workflow/orchestrator | Best ecosystem for data ingestion, NLP, LLM SDKs, geocoding. |
| **Primary DB** | **PostgreSQL + PostGIS** | Relational integrity for social data + first-class geospatial; temporal queries; mature everywhere. |
| **Vector DB** | **pgvector** (start) → dedicated (Qdrant/Weaviate) if scale demands | Semantic dedup + "related events" + recommendations. Start in Postgres to reduce moving parts. |
| **Cache / hot data** | **Redis** | Sessions, rate limits, pre-computed timeline buckets, feeds. |
| **Queue / streaming** | **Standard AMQP (RabbitMQ)** or a log (Kafka/Redpanda) at scale | Decouples ingestion from enrichment; backpressure; retries. |
| **Object store** | **S3-compatible** (MinIO locally, any cloud later) | Source HTML snapshots, screenshots, media thumbnails, exports. |
| **Search (text)** | Postgres FTS (start) → OpenSearch/Meilisearch later | Keyword search over events/comments. |
| **Auth** | OIDC provider (self-host Keycloak or managed) | Social login (Google/Facebook/Apple…) + email; provider-neutral via OIDC; account linkage. |
| **Admin portal** | Flutter Web + Admin API | One UI stack; RBAC + audited control of agents/budgets/feeds/moderation. |
| **Config** | DB-backed Config Service (+ pubsub hot-reload) | All agent behavior/budgets configurable at runtime without redeploy. |
| **LLM** | **Claude** (latest Sonnet/Opus per task) via API | Enrichment, dedup adjudication, summarization, relation extraction. |
| **Infra packaging** | Docker + docker-compose (dev), Kubernetes manifests/Helm (prod-ready, optional) | Runs on any cloud or on-prem. |
| **IaC** | Terraform (provider-agnostic modules) | Defer provider, keep portability. |

> Why FastAPI over Node for the API: the heavy, differentiated work here is the
> **data/AI pipeline**, which is Python-native. Keeping the API in Python lets the same
> team share models, schemas (Pydantic), and domain logic across API + agents. If a
> specific read path becomes a bottleneck, carve it out into a Go service later.

## 4. Key cross-cutting concerns

### 4.1 The temporal model (why it's special)
Events range from "5 minutes ago" to "Battle of Kadesh, ~1274 BC." We cannot treat
time as a single precise timestamp. Every event carries:
- a sortable instant (`event_time`),
- a **precision** (`exact_time | day | month | year | decade | century | era`),
- optional `event_end` for events with duration (wars, pandemics),
- calendar/era handling for pre-modern dates.

The timeline renderer and all range queries are precision-aware.

Critically, an event has **two kinds of time**: an **anchor time** (its position on the
main timeline — the main line is *bounded by sources*, i.e. we only plot what something
attested) and **subject time(s)** (deep-history periods the event merely discusses, which
populate a **sub-timeline** when the event is opened — recursively). Example: a 1956
article about the origin of life is plotted at **1956**; the "millions of years ago"
subject lives in that event's sub-timeline, not on the main line. Full detail in
[data-model.md §1.0](data-model.md).

### 4.2 Timeline scalability — server-side bucketing
Rendering 10M events on a zoomed-out timeline is impossible client-side. The Event API
exposes a **windowed, bucketed** endpoint: given a time range + zoom level + viewport
bbox + filters, the server returns pre-aggregated **buckets** (count, peak severity,
representative events) when zoomed out, and individual events when zoomed in. Buckets are
cached in Redis and rebuilt incrementally as agents publish events.

### 4.3 Severity scoring
A composite, recomputed score (0–100) blending:
- **Impact** (casualties/scale/economic effect — extracted by enricher),
- **Social** (likes, comments, follows, velocity),
- **Source corroboration** (# of independent sources referencing the event, source quality).

Severity drives color/size on the timeline & map. Formula and weights in
[ai-agents.md](ai-agents.md#severity) and tunable via config.

### 4.4 Source validation & trust
Every event links to **sources**. Sources have:
- an archived snapshot (object store) so links don't rot,
- a quality/reputation score,
- **community validation**: users vote a source as corroborating/disputing/irrelevant,
  with weighting by user reputation. The aggregate feeds back into severity + an event
  "confidence" badge. Anti-abuse via rate limits + reputation gating.

### 4.5 Notifications & "users with similar interests"
- **Subscriptions:** users follow timelines (a saved filter: topic, region, person, tag).
  New matching events fan out to subscribers (notification service → push + in-app).
- **Recommendations:** the recommendation service compares a user's interest vector
  (derived from follows, reactions, dwell time) against event embeddings + other users'
  vectors to surface new events and suggest follows. Privacy-respecting (opt-in signals).

### 4.6 Real-time
A WebSocket/SSE gateway pushes: live event publications within a user's active window,
new comments on watched events, and notifications. Falls back to polling on web if needed.

### 4.7 Access model — anonymous browse, authenticated interaction
- **Public (no account):** view the timeline/map, open events + sub-timelines, read
  sources & comments, and **search**. These endpoints are unauthenticated (rate-limited,
  cache-friendly).
- **Authenticated (account required):** all writes/interactions — reactions, comments,
  source validation, follows/subscriptions, personalized "for-you" feed.
- **Social login via OIDC** to minimize signup friction: Google, Facebook, Apple, etc. The
  first social login auto-provisions the user (no separate registration form). Multiple
  providers can be **linked to one account** (`user_identities`, see data-model.md §3.5).
- **Apple compliance note:** Apple's App Store guideline 4.8 requires offering **Sign in
  with Apple** on iOS if you offer other third-party social logins. Bake it in from the
  start to avoid review rejection.
- The API gateway enforces public-read / gated-write; the client shows a low-friction
  sign-in prompt only at the moment a user tries to interact.

### 4.8 Admin & configuration control plane
- A **Config Service** (DB-backed, versioned, audited, hot-reloaded via pubsub) holds all
  tunable behavior: agent enable/schedule/capabilities, per-agent & global **budgets**,
  feed definitions, dedup/severity thresholds, model selection, feature flags. Agents and
  APIs **read config at runtime** — no redeploy to change behavior.
- An **Admin Portal** (Flutter Web) + **Admin API** (strict RBAC, every action audited)
  let operators configure and **monitor** agents, budgets, feeds, moderation, and users.
- Full detail in [admin-portal.md](admin-portal.md).

## 5. Data flow: from world event → user's screen

1. **Ingestors** poll feeds (news APIs, GDELT, RSS, datasets) on schedules → raw items to queue.
2. **Normalizer** maps raw items to a candidate-event shape; extracts title, time, text, links.
3. **Deduper** embeds the candidate, searches the vector DB; merges into an existing event
   or creates a new one (LLM adjudicates ambiguous near-matches).
4. **Enricher (LLM)** extracts entities (people, orgs, places), summary, impact signals,
   categories/tags. Only runs on new/changed events → cost control.
5. **Geocoder** resolves places → coordinates (PostGIS), attaches to the event.
6. **Relation-linker** finds historically/geographically/person-related events (vector +
   graph queries) and writes relations for "related events" navigation.
7. **Severity-scorer** computes the composite score.
8. **Publisher** writes canonical event, invalidates/updates timeline buckets, emits a
   "new event" message → notification + recommendation + real-time gateways.
9. **Clients** request timeline windows/buckets, render, and stream live updates.

## 6. Security, privacy, abuse

- AuthN via OIDC; AuthZ via role/scope (user, moderator, admin) + per-resource checks.
- All source links archived to prevent manipulation; original URL retained for audit.
- Rate limiting at the gateway; reputation gating on votes/comments; spam/abuse moderation queue.
- PII minimization; explicit opt-in for interest signals used in recommendations.
- Content moderation pipeline for user comments (LLM-assisted flagging + human review).

## 7. Observability & ops

- Structured logging, distributed tracing (OpenTelemetry), metrics (Prometheus-compatible).
- Agent pipeline dashboards: ingestion lag, dedup rate, LLM token spend, enrichment errors.
- Cost guardrails: per-day LLM budget caps; degrade to feed-only enrichment when exceeded.

See [roadmap.md](roadmap.md) for how these components are sequenced into deliverable phases.
