# db/ — Database schema & migrations

Single source of truth for the Postgres schema (the data model in
[../docs/data-model.md](../docs/data-model.md)). Extensions (PostGIS, pgvector, pg_trgm)
are enabled by the Postgres image init; **table migrations live here**.

| Path | What |
|------|------|
| `alembic.ini` | Alembic config (DB URL injected from `chronos_core.settings` — no secrets in git). |
| `migrations/env.py` | Uses `chronos_core.models` metadata as the schema source of truth. |
| `migrations/versions/0001_initial.py` | Phase-1 schema: events (dual-time) + references + sources + ingest + config. |

## Usage
```sh
pip install -e ../packages/core alembic
cd db
alembic upgrade head          # apply (DATABASE_URL via env/.env)
alembic upgrade head --sql    # render DDL without a DB (offline)
alembic revision -m "msg"     # new migration (then hand-edit/autogenerate)
```
In the stack this runs automatically via the `migrate` service before `api`/`agents` start.

Conventions: one logical change per migration, forward + reversible where practical, never
edit a shipped migration (add a new one). The DB is designed to be partitionable/splittable
later (see data-model.md §5) — keep migrations compatible with that.
