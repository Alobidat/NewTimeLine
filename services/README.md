# services/ — Backend services

Python services. Each is **independently runnable**, stateless, and talks to the shared
data layer (Postgres / Redis / RabbitMQ / S3) via standard interfaces. Shared schemas and
domain types live in [`../packages/`](../packages/) so services stay decoupled.

| Dir | What | Status |
|-----|------|--------|
| `api/` | Public + app API (events, timeline windows, sub-timelines, map, social, search) — FastAPI | Planned (Phase 1) |
| `agents/` | The feed-first agent pipeline workers (ingest → enrich → dedup → geocode → link → score → publish) | Planned (Phase 1/3) |
| `admin-api/` | Admin/config control-plane API (RBAC, audited) | Planned (Phase 3) |

Conventions: small single-responsibility modules, public API documented in each package's
`__init__.py`/README, `ruff` lint+format, async, idempotent + retry-safe workers. See
[../docs/architecture.md](../docs/architecture.md) and
[../docs/ai-agents.md](../docs/ai-agents.md).
