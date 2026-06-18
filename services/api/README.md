# chronos-api — Event API

Public, read-mostly FastAPI service backing the timeline/map/event views. Anonymous reads
(ADR-0007); writes are for manual/admin use now (auth gating lands in Phase 4).

## Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/healthz` | Liveness |
| GET | `/readyz` | Readiness (DB reachable) |
| GET | `/timeline` | Windowed timeline: events when sparse, **buckets** when dense (heatline). Params: `t0,t1` (signed years), `bbox`, `category`, `min_severity`, `max_events`, `buckets` |
| GET | `/map` | Geolocated events within a `bbox` (+ optional time window), heaviest first |
| GET | `/events/{id}` | Full event: summary, sources, sub-timeline references |
| GET | `/events/{id}/subtimeline` | Deep-time subject references (the sub-timeline) |
| POST | `/events` | Create an event (manual/admin; agents use `chronos_core.repository`) |

Time is a **signed year** (ADR-0012): `t0=-4000000` … `t1=2026.5`. Interactive docs at
`/docs` when running.

## Layout
```
src/chronos_api/
  main.py        app factory + lifespan (seeds Config Service defaults)
  deps.py        request-scoped DB session
  queries.py     read queries (timeline/buckets/map/detail/subtimeline) with PostGIS projection
  routers/       health · events · timeline
```
Write logic is shared via `chronos_core.repository` (not duplicated here).

## Run
```sh
pip install -e ../../packages/core -e ".[dev]"
# point DATABASE_URL at a migrated DB, then:
uvicorn chronos_api.main:app --reload
```
Or via the stack: `docker compose up api` (see root `docker-compose.yml`).
