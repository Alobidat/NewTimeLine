# Chronos — A Living Timeline of the World

> Working codename for the **NewTimeLine** project.

Chronos is a cross-platform social app that turns world events — happening now and
throughout history — into a navigable, graphically rich **timeline**. AI agents
continuously hunt for events from news and data feeds, enrich them with location,
people, and historical context, score their severity, and plot them on a timeline +
map. Users navigate through time, inspect sources, react, comment, and collectively
**validate** the sources behind each event.

## What's in this repo right now

This is the **architecture & planning** phase. No application code yet — the documents
below define the system before we build it.

| Doc | What it covers |
|-----|----------------|
| [docs/architecture.md](docs/architecture.md) | System architecture, components, tech stack, data flow |
| [docs/data-model.md](docs/data-model.md) | Database schema (events, sources, users, geo, temporal model) |
| [docs/ai-agents.md](docs/ai-agents.md) | The feed-first tiered agent pipeline (ingest → enrich → dedup → score) |
| [docs/admin-portal.md](docs/admin-portal.md) | Admin control plane: agent config, budgets, feeds, moderation, monitoring + the Config Service |
| [docs/timeline-ux.md](docs/timeline-ux.md) | The "magical timeline" UX, sub-timelines, severity visualization, map, anon vs signed-in |
| [docs/roadmap.md](docs/roadmap.md) | Phased build plan from MVP to full platform |
| [docs/engineering-standards.md](docs/engineering-standards.md) | **Standing rules for every phase** — clean code, small modules, token-economy-first |
| [docs/infrastructure.md](docs/infrastructure.md) | Proxmox LXC hosting plan (local + public test) |
| [docs/decisions.md](docs/decisions.md) | Key decisions summary + open questions |
| [docs/decision-log.md](docs/decision-log.md) | Append-only ADR log — so we never start from scratch |

## Repo layout

```
apps/        Flutter clients (mobile + Flutter Web admin)      → apps/README.md
services/    Backend services (api, agents, admin-api)          → services/README.md
packages/    Shared libraries (schemas, domain, clients, ui)    → packages/README.md
db/          Schema migrations (single source of truth)         → db/README.md
infra/       Docker image(s), Proxmox + Terraform provisioning  → infra/README.md
docs/        Architecture, data model, decisions, standards     → docs/
docker-compose.yml   Local backing-services stack (Phase 0)
```
Every dir has a short README — read it instead of scanning the source (see the
[engineering standards](docs/engineering-standards.md)).

## Getting started (Phase 0 — backing services)

Phase 0 stands up the data layer (Postgres+PostGIS+pgvector, Redis, RabbitMQ, MinIO).
Run on a machine with Docker (the Proxmox `app-host`, or local):

```sh
cp .env.example .env      # set strong secrets — .env is gitignored
docker compose up -d --build
docker compose ps         # all services should be healthy
# or: make up / make ps   (see `make help`)
```
App services (API, agents, admin) arrive in later phases — see [docs/roadmap.md](docs/roadmap.md).

## Core decisions (locked)

- **Clients:** Flutter (one codebase → Android, iOS, Windows/macOS, Web)
- **AI agents:** Feed-first tiered pipeline (structured news/event feeds first, LLM only for enrichment/dedup) to control cost
- **Historical depth:** Source-bounded main timeline + a **dual-time model** — events sit at their *anchor time*; deep-history subjects they discuss live in a **sub-timeline** revealed on open (the 1956 → "origin of life" example)
- **Access:** Anonymous browse/search; **social login** (Google/Facebook/Apple…) only when a user interacts
- **Admin:** Admin Portal + **Config Service** — all agent behavior, budgets & feeds configurable at runtime, monitored, audited
- **Infra:** Cloud-agnostic design now; pick provider at build time
- **First deliverable:** This architecture + plan

See [docs/decisions.md](docs/decisions.md) for the full rationale and open questions.

## The 30-second mental model

```
        News/Event Feeds            Historical Datasets
              │                            │
              ▼                            ▼
   ┌───────────────────────────────────────────────┐
   │   AI AGENT PIPELINE (background, continuous)    │
   │   ingest → normalize → dedup → enrich (LLM) →   │
   │   geocode → link related → score severity       │
   └───────────────────────────────────────────────┘
              │  writes canonical events
              ▼
   ┌───────────────────────────────────────────────┐
   │  DATA: Postgres+PostGIS · Vector DB · Object    │
   │  store (source snapshots) · Cache/Queue         │
   └───────────────────────────────────────────────┘
              │  serves
              ▼
   ┌───────────────────────────────────────────────┐
   │  API (events, timeline windows, social, search) │
   │  + real-time (notifications, live updates)       │
   └───────────────────────────────────────────────┘
              │
              ▼
   ┌───────────────────────────────────────────────┐
   │  FLUTTER CLIENTS — magical timeline + map +     │
   │  sources + reactions/comments + source voting   │
   │  (Android · iOS · Windows · macOS · Web)        │
   └───────────────────────────────────────────────┘
```
