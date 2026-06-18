# Decisions & Open Questions

## Locked decisions (this session)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | First deliverable | **Architecture + plan** (no app code yet) | Validate direction before investing build effort on a large system. |
| 2 | Client stack | **Flutter** (one codebase → Android, iOS, Windows, macOS, Web) | Single codebase across all required platforms; strong custom-graphics/animation story for the timeline; good map support. |
| 3 | AI agents | **Feed-first tiered pipeline** (structured feeds first; LLM only for enrich/dedup) | Controls ongoing cost; most events arrive with $0 LLM; LLM spent only where it adds value. |
| 4 | Infra/cloud | **Cloud-agnostic now; pick provider at build time** | Keeps options open; containerized + standard interfaces (Postgres, S3-API, AMQP). |
| 5 | Historical depth | **Source-bounded main timeline + dual-time model** | Main timeline only plots what sources attest, at each event's **anchor time**. Deep-history subjects an event *discusses* live in a **sub-timeline** (subject time) revealed on open — recursively. (1956 article → 1956 on main line; "origin of life" in its sub-timeline.) See [data-model.md §1.0](data-model.md). |
| 6 | Admin & config | **Admin Portal + DB-backed Config Service** | All agent behavior, budgets, capabilities, feeds, thresholds configurable at runtime (no redeploy), monitored, RBAC + audited. See [admin-portal.md](admin-portal.md). |
| 7 | Access & auth | **Anonymous browse/search; auth-gated interaction; social login** | Anyone views/searches without an account; reactions/comments/validation/follows require sign-in. **Social login** (Google/Facebook/Apple…) via OIDC, first login auto-provisions (no form), multi-provider **account linkage**. Apple sign-in required on iOS. See [architecture.md §4.7](architecture.md). |

## Derived recommendations (mine, open to change)

| Area | Recommendation | Note |
|------|----------------|------|
| API services | Python + FastAPI | Shares language/models with the Python agent pipeline. Swap a hot path to Go later if needed. |
| Primary DB | PostgreSQL + PostGIS | Geo + relational + temporal in one mature, portable engine. |
| Vector search | pgvector first | Fewer moving parts; migrate to Qdrant/Weaviate only if scale demands. |
| Maps | MapLibre GL + vector tiles | Open, self-hostable, no per-render vendor cost. |
| Queue | RabbitMQ (or Kafka/Redpanda at scale) | Decouples ingestion from enrichment. |
| Object store | S3-compatible (MinIO locally) | Archived source snapshots; portable. |
| LLM | Claude, tiered by task | Cheaper tier for high-volume enrich/dedup; stronger tier for Tier-3 dig. |

## Resolved this session
- **Historical depth** → source-bounded main timeline + dual-time/sub-timeline model (#5).
- **Accounts at launch** → anonymous browse/search, auth-gated interaction, social login (#7).
- **Admin/config** → Admin Portal + Config Service (#6).

## Open questions (need your input before/within build phases)

1. **Initial geographic / language scope.** Global + English first, or multi-language from
   the start? (Affects feeds, NLP, and UI i18n. Recommend English-first, i18n-ready.)
2. **Moderation posture.** How heavy a human moderation layer at launch vs LLM-assisted
   only? (Affects Phase 4 staffing/tooling.)
3. **Monetization / cost ceiling.** Is there a target monthly infra+LLM budget for v1? This
   sets the default daily token cap (now enforced via the Config Service) and feed choices.
4. **Source/feed licensing.** Some news/event APIs have usage/licensing terms; confirm
   which feeds are acceptable (GDELT + Wikidata are open; commercial news APIs vary).
5. **Which social login providers for v1?** Recommend Google + Apple (iOS) + Facebook to
   start; add others later. Confirm the set.
6. **Admin portal frontend.** Flutter Web (one stack, recommended) vs a dedicated web-admin
   framework (richer data grids). Confirm preference.
7. **Brand / name.** "Chronos" is a working codename; confirm or replace.
8. **Compliance scope.** GDPR/CCPA expected (likely yes given "across the globe"); any
   other regimes (e.g. regional data residency)?

## How to proceed
When you're ready to build, the recommended first increment is **Phase 0 → Phase 1 →
Phase 2** (foundations + event spine + read-only magical timeline), which yields a
demonstrable product without yet incurring agent LLM cost. See [roadmap.md](roadmap.md).
