# Engineering Standards (apply to EVERY phase)

These are standing rules for the whole project. They exist to keep the codebase clean,
scalable, and — above all — **cheap to work on with an AI assistant later**. Read this
before writing code in any phase.

## 0. Prime directive: token economy
Saving AI tokens is our **main driver**. Every practice below ladders up to one goal: a
future session (human or AI) should understand any module by reading a *small* amount of
text, not by scanning the whole codebase. Concretely:

- **Self-describing structure.** Every top-level dir and every module has a short
  `README.md` that says *what it does, its public interface, and what it depends on*. An
  assistant reads the README, not all the source.
- **Document the logic, not the obvious.** Public functions/classes get a one-line
  docstring stating intent + contract (inputs, outputs, side effects). Skip narrating
  trivial code.
- **Decisions are written down once.** See [decision-log.md](decision-log.md). We never
  re-derive a decision we already made. If we change our mind, we append a new entry.
- **Stable interfaces, documented.** Cross-module contracts (API schemas, queue message
  shapes, DB tables) are documented in one canonical place so callers don't read
  implementations.

## 1. Code style
- **Clean, consistent indentation.** Enforced by formatters, not by hand:
  - Python → `ruff` (lint) + `ruff format`/`black`. 4-space indent.
  - Dart/Flutter → `dart format` + `flutter analyze`. 2-space indent.
  - SQL → lowercase keywords optional but be consistent; one statement per migration step.
  - YAML/JSON/Markdown → 2-space indent; `prettier` where applicable.
- **Short comments, only when needed.** Explain *why*, not *what*. No commented-out code in
  commits.
- **Clear names over comments.** A well-named function rarely needs a comment.

## 2. Small files, clear scope
- **Soft cap ~300 lines per file** (hard smell at ~400). When a file grows past it, split
  by responsibility.
- **One responsibility per file/module.** A file's name should predict its contents.
- **Split logic into modules with clear scope** (the "DLL" idea):
  - Python: packages with explicit public API in `__init__.py`; internal helpers prefixed
    `_` or kept in `_internal` submodules. Each service is independently runnable.
  - Dart: feature-first libraries/packages; expose a thin public API via barrel files.
  - Shared, reusable logic lives in [`packages/`](../packages/) — never duplicated across
    services.
- **Dependencies point inward / one direction.** No circular module dependencies. A module
  declares its dependencies at the top of its README.

## 3. Scalability by design (cheap now, scalable later)
- **Stateless services** behind the gateway; state lives in Postgres/Redis/queue/object
  store. Lets us scale horizontally without rework.
- **Async + queue-decoupled** agent stages (each independently scalable, idempotent,
  retry-safe — keyed by stable ids).
- **Config over code** ([admin-portal.md](admin-portal.md)): tunables (budgets, schedules,
  thresholds) are runtime config, not constants — no redeploy to change behavior.
- **Don't prematurely optimize, but don't block scale.** Pick designs that *allow* scaling
  (partitionable tables, bucketed timeline reads) even if we run single-instance for v1.
- **Cloud-agnostic interfaces.** Talk to Postgres, an S3-API, an AMQP queue, an OIDC
  provider — not vendor SDKs — so the host stays swappable.

## 4. Project layout (monorepo)
```
apps/        Flutter clients (mobile/desktop/web) + Flutter Web admin portal
services/    Backend services (api, agents, …) — each independently runnable
packages/    Shared libraries (schemas, domain types, clients) reused across services
db/          Migrations + DB tooling (single source of truth for schema)
infra/       Docker Compose, Terraform stubs, Proxmox provisioning
docs/        Architecture, data model, decisions, standards (this dir)
```
Each of these has a `README.md`. Add new top-level dirs sparingly and document them.

## 5. Git & change hygiene
- **Conventional Commits** (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `ci:`). Small,
  focused commits with clear messages — they are part of the project's memory.
- **Branch per change**, PR into `main`. Never commit secrets (use `.env`, gitignored).
- **Pre-commit hooks** run formatters/linters so style never reaches review.
- CI must pass (lint + tests + build) before merge.

## 6. Testing
- Unit tests for domain logic and agent stages (pure functions are easy + cheap to test).
- Contract tests for API schemas and queue messages (so callers stay decoupled).
- Don't chase 100% coverage; cover the logic that would be expensive to get wrong.

## 7. Documentation map (where things live, so we don't re-read code)
| Question | Read this |
|----------|-----------|
| What is this project / how do pieces fit? | [architecture.md](architecture.md) |
| What's the DB schema / data shapes? | [data-model.md](data-model.md) |
| How do the agents work / cost controls? | [ai-agents.md](ai-agents.md) |
| Admin/config/budgets? | [admin-portal.md](admin-portal.md) |
| Timeline/UX behavior? | [timeline-ux.md](timeline-ux.md) |
| Why did we choose X? | [decision-log.md](decision-log.md) + [decisions.md](decisions.md) |
| How/where do we deploy? | [infrastructure.md](infrastructure.md) |
| What's the build order? | [roadmap.md](roadmap.md) |
| How do I work in module Y? | `Y/README.md` |

> Rule of thumb: if you had to read source code to answer a "what/why" question, the docs
> were incomplete — fix the doc in the same PR.
