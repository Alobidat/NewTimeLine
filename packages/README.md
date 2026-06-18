# packages/ — Shared libraries

Reusable code shared across services/apps so logic is **defined once, never duplicated**
(token-economy rule). Each package has a clear scope and a documented public API.

Planned packages (added as needed):
| Package | Scope |
|---------|-------|
| `schemas/` (Python) | Pydantic models for events, sources, queue messages, API DTOs — the canonical data shapes shared by `api` + `agents`. |
| `domain/` (Python) | Pure domain logic (severity scoring, temporal/precision helpers, dedup keys) — no I/O, easy to test. |
| `clients/` (Python) | Thin wrappers for Postgres/Redis/AMQP/S3/LLM with config-driven setup. |
| `ui_kit/` (Dart) | Shared Flutter widgets/design system used by `mobile` + `admin`. |

Rule: if two services need the same logic/shape, it belongs here. See
[../docs/engineering-standards.md](../docs/engineering-standards.md) §2.
