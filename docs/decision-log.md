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
