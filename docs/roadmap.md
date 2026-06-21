# Build Roadmap

A phased plan from nothing → full platform. Each phase ends in something demonstrable.
Phases are sequenced to de-risk the hardest/most-differentiating parts early (temporal
model, timeline rendering, the agent pipeline) while keeping every phase shippable.

## Guiding sequencing principles
1. **Prove the spine first:** event data model + one ingestor + a real timeline render.
   Everything else hangs off this.
2. **Vertical slices, not horizontal layers:** each phase delivers end-to-end value.
3. **Cost-controlled AI from day one:** feeds before LLM; budget caps wired early.
4. **Defer scale, not correctness:** start single-region/managed; design leaves room to grow.

---

## Phase 0 — Foundations (repo, infra skeleton) ✅ DONE
**Goal:** a monorepo and local dev environment everything else builds on.
- Monorepo layout (`apps/`, `services/`, `db/`, `infra/`, `docs/`).
- Docker Compose for local: Postgres+PostGIS+pgvector, Redis, MinIO (S3), RabbitMQ.
- CI skeleton (lint, test, build), pre-commit, formatting.
- Provider-neutral Terraform module stubs (filled when the cloud is chosen).
**Done when:** `docker compose up` brings up all backing services locally.

## Phase 1 — The spine: events + temporal model + one ingestor ✅ DONE
**Goal:** real events flowing into the DB from a free feed, queryable by time/place.
**Delivered:** `chronos-core` (models/schemas/domain/config, 33 unit tests), Alembic
migration (offline-validated), `chronos-api` (7 endpoints), `chronos-agents` (RSS ingest +
Wikidata seed, Tier-1 no LLM), Config Service seeded on startup, all wired into compose.
Time axis changed to signed numeric year (ADR-0012).
- Implement the `events` schema + **dual-time model** (anchor time + `event_references`
  subject time) + precision + PostGIS geom (db/migrations).
- Stand up the **Config Service** (DB-backed settings + audit) so agents are configurable
  from day one — even before the admin UI exists.
- Event API (FastAPI): create/read events, **windowed timeline query**, map bbox query,
  and **sub-timeline query** (an event's subject references).
- One **Tier-1 ingestor** (e.g. GDELT or a news RSS) → Normalizer → Publisher (no LLM yet;
  rule-based only).
- Seed a batch of **historical events** from Wikidata to populate deep time.
**Done when:** the API returns real events for a given time window + map bbox, and a
sub-timeline for an event.

## Phase 2 — The magical timeline (Flutter client, read-only) ✅ DONE
**Goal:** the signature experience, consuming Phase-1 data.
**Delivered:** Flutter app (web+windows) — scrub/zoom timeline (CustomPainter), severity
points/bands, density heatline from server buckets, event detail + sub-timeline drill-down,
**linked map** (flutter_map, ADR-0013) sharing one time window with the timeline, anonymous.
Pure-Dart time/geo math unit-tested (16 tests), analyze clean, web build compiles.
- Flutter app shell (Android/iOS/desktop/web targets building).
- **Timeline widget:** scrub + log zoom, points vs bands, severity color/height,
  density heatline from server buckets.
- **Map layer** (MapLibre) linked to the timeline.
- **Event detail** panel: summary, time (precision-aware), place, sources list.
- **Sub-timeline drill-down:** opening an event reveals a sub-timeline of its subject
  references on the subject-time axis (the 1956→deep-time example).
- **Anonymous browsing:** all of the above works with no account (public read APIs).
- Server-side **bucketing** endpoint + Redis cache for zoomed-out performance.
**Done when:** an anonymous user can scrub across millennia, see events on map+timeline,
open an event, and drill into its historical sub-timeline.

## Phase 3 — The agent pipeline (enrichment, dedup, geo, severity) 🟡 3a + graph slice DONE
**Goal:** events arrive enriched, deduped, geocoded, and scored — automatically.
**Phase 3a delivered:** provider-agnostic LLM layer (`chronos_core.llm`) — vLLM/Ollama/OpenAI
+ Claude behind one interface — with a **budget-aware router that auto-switches to a local
LLM when the cloud token budget is spent** (ADR-0014/0015), all config-driven. The
**Enricher (Tier-2)** runs on it: schema-validated summary/category/tags/impact + deep-time
references → populates sub-timelines, impact-aware severity. `agents enrich` command. Router
unit-tested (budget exhaustion + error fallback).
**Phase 3b — entity-anchored history graph slice delivered** (ADR-0016/0017, migration
0002): `entities` + `event_entities` (the enricher now tags actors/locations), a directed
`event_relations` graph, a Tier-1 **relation-linker** (`agents relate`) building edges from
shared entities + time order, and the **dig** API — `/search`, `/entities`,
`/events/by-entities` (the "US ↔ Iran" intersection), `/events/{id}/related`, and the
recursive `/events/{id}/chain` (back = led-to / forward = caused). Plus the **media**
foundation (`media` + `event_media`) so event detail can carry images/video, with links
addable later by users or new sources.
**Phase 3b — media archival delivered** (ADR-0018, migration 0003): a capture-first policy
engine + `media-fetch`/`media-check` workers store hot/sensitive media locally (object
store) before it vanishes under pressure, link durable corroborated media, and release
local copies once they prove durable; `media_sources` tracks per-host availability. RSS
ingest now discovers media (enclosures/`media:content`/thumbnails) and applies the policy.
**Phase 3b — Admin Portal backend foundation delivered** (ADR-0019, migration 0004): a
**manifest-driven, schema-driven** control plane so the portal self-extends as components are
added. Component registry (`chronos_core.registry`) + typed config specs
(`chronos_core.config_spec`, now the single source of truth for `DEFAULTS` + validation) +
`agent_runs` history (CLI wraps runs; health derived by pure `chronos_core.domain.health`) +
the **Admin API** (`/admin/overview|components|config|runs|storage|system|users`, bearer-token
gated, audited).
**Phase 3b — Admin Portal client delivered** (`apps/admin`): a Flutter app (web + apps, one
codebase) rendering from the Admin API — Overview dashboard, Components list + detail (health,
capabilities, enable/disable, schema-driven config editor), Config, Runs, Storage, System
screens; responsive rail/bottom-nav; polling-based. flutter analyze + test green (CI matrix).
**3b remaining:** dedup (pgvector), geocoder, image thumbnailing + signed media serving,
queue/scheduler (run-now execution), admin real-time streaming + deeper resource metrics.
- Stand up the queue-based worker pipeline (Normalizer → Deduper → Enricher → Geocoder →
  Relation-linker → Severity-scorer → Publisher).
- **Deduper** with pgvector + rule fast-path + LLM adjudication for ambiguous cases.
- **Enricher (Tier-2 LLM):** schema-validated entity/summary/impact extraction; runs only
  on new/changed events; **daily token budget cap** + caching.
- **Geocoder** (structured-first), **severity scorer** with transparent breakdown.
- Add 2–3 more ingestors (a news API, USGS/disaster feed, more Wikidata).
- **Enricher also extracts `event_references`** (subject times) → populates sub-timelines.
- **Minimal Admin Portal console:** enable/disable agents, set schedules & **budgets**,
  manage feeds, view live spend + pipeline health (reads/writes the Config Service).
- Observability: ingestion lag, dedup rate, token spend dashboards.
**Done when:** new world events appear enriched+scored within minutes, under budget, and an
operator can tune agents/budgets/feeds from the admin console.

## Phase 3c — Event presentation, location integrity & live search 🟡 IN PROGRESS
**Goal:** every event is a complete, richly-presented article that *always* highlights on the
map and is *always* connected to related events; search both reads and grows the corpus.
Builds on the existing schema (no new core tables). Full design:
[event-presentation.md](event-presentation.md) (ADR-0020…0023).
- **A — Location integrity & map fix** *(start here; the reported "huge problem")*: enforce
  Time+Location+Actors per event via a **resolution cascade** (geom → `geo_label` →
  `location` entities → text analysis → news-agency country) + multi-location highlighting +
  data-integrity flagging; fix the client's silent no-highlight fallback; backfill existing
  events. (ADR-0020)
- **B — Article format & rich media:** one standard layout across sheet + panel (title →
  media → summary → subject w/ inline links → actors → **related-events footer** → sources);
  expandable, clips-first media gallery (carousel, pinch-zoom, fullscreen video). (ADR-0021/0023)
- **C — Rich search + live collection:** search by location/actor/keyword (faceted), and a
  search **triggers background collection** (Redis run-queue → on-demand collection agent →
  pipeline → SSE stream) so results refresh as new events arrive. (ADR-0022)
- **D — Source expansion & media-richness:** source-adapter registry (RSS/Wikidata/Wikipedia/
  news APIs) widening both background and search-driven collection; **no text-only events**
  (ensure ≥1 image, prefer clips). (ADR-0023)
**Done when:** every event shows the article layout with media + related links, highlights one
or more countries on the map, and a search returns existing results while live-collecting and
streaming in new ones.

## Phase 4 — Social layer + accounts
**Goal:** users, reactions, comments, and the source-validation system.
- **Social login (OIDC):** Google, Facebook, **Apple** (iOS-required), email; first login
  auto-provisions the account (no registration form); **account linkage** across providers.
- Public-read / **auth-gated-write** enforcement; in-client sign-in prompt on interaction,
  preserving the pending action.
- User profiles; reputation scaffolding.
- Reactions (like/dislike/important/doubt) → feed social severity component.
- Threaded comments + moderation queue (LLM-assisted flagging).
- **Source validation:** corroborate/dispute/irrelevant voting, reputation-weighted,
  feeding event `confidence` + source `quality_score`.
- **Admin Portal — moderation:** comment/flag queue, event retract/merge, source disputes,
  user admin (roles, suspend, reputation overrides).
**Done when:** anonymous users still browse freely; signed-in users react, discuss, and
validate sources; moderators manage content from the portal.

## Phase 5 — Subscriptions, notifications, recommendations
**Goal:** the system reaches out — keeps users informed and grows engagement.
- **Timelines** (saved filters) + follow/subscribe (timelines, entities, events).
- **Notification service:** match published events against subscription filters → fan-out;
  push (mobile) + in-app; real-time gateway (WebSocket/SSE) for live updates.
- **Recommendations:** interest vectors + event embeddings → "for you" + suggested follows
  ("users with similar interests"). Onboarding interest picker.
**Done when:** subscribers get notified of new matching events; discovery rail is live.

## Phase 6 — Deep historical dig (Tier-3) + relation graph polish
**Goal:** the "dig into history" magic for important events.
- Tier-3 on-demand research agent (fan-out research → verify → synthesize), severity/
  interest-gated and budget-capped.
- Strengthen `event_relations` (causal/precursor/thematic) and the related-events UX;
  entity-pivot navigation; time-lapse play mode.
**Done when:** high-severity events show rich, sourced historical context + related chains.

## Phase 7 — Hardening, scale, launch readiness
**Goal:** production-grade.
- Pick the cloud; fill Terraform; deploy (k8s or managed equivalents).
- Load testing of timeline/bucketing; partitioning if needed; CDN for tiles/snapshots.
- Security review, abuse/rate-limit tuning, moderation workflows, GDPR/privacy controls.
- App store + web release pipelines.
**Done when:** the platform is deployed, monitored, and meets perf/security bars.

---

## Risk register (watch these early)
| Risk | Mitigation | Phase |
|------|------------|-------|
| Timeline perf with huge event counts | Server bucketing + LOD + prefetch — built in Phase 2 | 2 |
| LLM cost runaway | Feed-first + enrich-only-new + daily budget cap + cache | 1,3 |
| Event dedup quality (dupes or wrong merges) | Vector + rules fast-path, LLM only on ambiguous, never discard sources | 3 |
| Temporal correctness (BC dates, precision) | Precision model + precision-aware queries from Phase 1 | 1 |
| Misinformation / source trust | Corroboration + community validation + confidence badges | 4 |
| Feed reliability / rate limits | Multiple feeds, idempotent ingest, replay from `ingest_items` | 1,3 |
| Notification fan-out scale | Filter-matching service + queue; partition later | 5 |

## What to build first if you want a single demo ASAP
The fastest credible demo is **Phase 1 + Phase 2** (spine + read-only magical timeline,
seeded from Wikidata + one live feed). That shows the core "wow" without yet paying for the
agent LLM costs or building accounts. Recommend doing those two, demoing, then proceeding.
