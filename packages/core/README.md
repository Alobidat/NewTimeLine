# chronos-core

Shared Python library — the **canonical data shapes and pure logic** reused by every
backend service (so logic is defined once; token-economy rule).

## Public API (import surface)
| Module | What | Depends on |
|--------|------|-----------|
| `chronos_core.domain.temporal` | Signed-year time axis: precision windows, `materialize_span`, `overlaps`, datetime↔year (ADR-0012) | stdlib only |
| `chronos_core.domain.severity` | Composite 0..100 severity scoring + weights | stdlib only |
| `chronos_core.models` | SQLAlchemy ORM (events, event_references, sources, ingest_items, config) — the schema | SQLAlchemy, GeoAlchemy2, pgvector |
| `chronos_core.schemas` | Pydantic API DTOs (EventRead/Detail/Create, Timeline*, Source*) | pydantic |
| `chronos_core.db` | Async engine + `session_scope()` | SQLAlchemy[asyncio], asyncpg |
| `chronos_core.config_service` | DB-backed runtime config: `get/get_many/set_value/ensure_defaults` (ADR-0006) | models |
| `chronos_core.interactions_repo` | Comments / reactions / source-votes / user event-links write+read helpers (ADR-0025) | models |
| `chronos_core.social_repo` | Follow/unfollow, promote/demote, activity-log recording + follower/following counts (ADR-0025/0028) | models |
| `chronos_core.interest` | Decayed weighted **interest profile** from the activity log (ADR-0028) | models, config_service |
| `chronos_core.upload` | Create a pending user **video event** (hero media + entities + links) from an uploaded clip (ADR-0029) | models, repository |
| `chronos_core.settings` | Env-based `Settings` (connection URLs) | pydantic-settings |

## Notes
- `domain.*` is pure (stdlib only) → unit-tested without a DB (see `tests/`).
- Importing `chronos_core.models` registers all tables on `Base.metadata` (Alembic uses this).
- The ORM is the schema's single source of truth; migrations live in [`../../db/`](../../db/).

## Dev
```sh
pip install -e ".[dev]"
pytest            # runs the pure-domain tests
ruff check src    # lint
```
