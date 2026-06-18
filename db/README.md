# db/ — Database schema & migrations

Single source of truth for the Postgres schema (the data model in
[../docs/data-model.md](../docs/data-model.md)). Extensions (PostGIS, pgvector, pg_trgm)
are enabled by the Postgres image init; **table migrations live here**.

| Dir | What |
|-----|------|
| `migrations/` | Ordered, versioned schema migrations (Phase 1+). Tooling chosen with the API (e.g. Alembic for the FastAPI/SQLAlchemy stack). |

Conventions: one logical change per migration, forward + reversible where practical, never
edit a shipped migration (add a new one). The DB is designed to be partitionable/splittable
later (see data-model.md §5) — keep migrations compatible with that.
