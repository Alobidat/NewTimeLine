# services/ — Backend services

Python services. Each is **independently runnable**, stateless, and talks to the shared
data layer (Postgres / Redis / RabbitMQ / S3) via standard interfaces. Shared schemas and
domain types live in [`../packages/`](../packages/) so services stay decoupled.

| Dir | What | Status |
|-----|------|--------|
| `api/` | Public API: events, timeline windows+buckets, map bbox, sub-timeline (FastAPI) | **Phase 1 ✅** (social/search later) |
| `agents/` | Feed-first pipeline. Phase 1: Tier-1 RSS ingest + Wikidata seed (no LLM) | **Phase 1 ✅** (enrich/dedup/geocode Phase 3) |
| `admin-api/` | Admin/config control-plane API (RBAC, audited) | Planned (Phase 3) |

Conventions: small single-responsibility modules, public API documented in each package's
`__init__.py`/README, `ruff` lint+format, async, idempotent + retry-safe workers. See
[../docs/architecture.md](../docs/architecture.md) and
[../docs/ai-agents.md](../docs/ai-agents.md).
