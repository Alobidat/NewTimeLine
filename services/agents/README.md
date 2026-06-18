# chronos-agents — feed-first pipeline (Phase 1)

Tier-1 only (no LLM): pull structured feeds, normalize, publish. Enrich/dedup/geocode/
relation/severity-LLM stages arrive in Phase 3 (docs/ai-agents.md).

## Stages (Phase 1)
```
ingest (RSS) ──► normalize ──► publish        (+ Wikidata historical seed)
```
| Module | Role |
|--------|------|
| `normalize.py` | **Pure** raw item → `CandidateEvent` (RSS + Wikidata). BC-year + WKT parsing live here (unit-tested). |
| `publish.py` | Write a candidate via `chronos_core.repository`; simple source-URL dedup. |
| `ingest_rss.py` | Poll feeds (from Config Service) → store `ingest_items` → publish. |
| `seed_wikidata.py` | SPARQL pull of dated, geolocated historical events → populate deep time + map. |
| `run.py` | CLI entrypoint. |

## Config-driven (no redeploy to change)
Reads from the Config Service: `agents.ingest.rss.feeds`, `…enabled`,
`…max_items_per_feed`, `severity.weights`. Tune via the admin portal (Phase 3) or DB.

## Run
```sh
pip install -e ../../packages/core -e ".[dev]"
# with DATABASE_URL pointing at a migrated DB:
python -m chronos_agents.run seed-wikidata --limit 300   # historical seed (run once)
python -m chronos_agents.run ingest-rss                  # poll news feeds
```
Or via the stack:
```sh
docker compose run --rm agents seed-wikidata --limit 300
docker compose run --rm agents ingest-rss
```

## Notes
- Idempotent: RSS deduped by `(feed, external_id)` in `ingest_items`; publish deduped by
  source URL. Re-running is safe.
- No secrets/keys needed in Phase 1 (GDELT-free; RSS + Wikidata are open). Wikidata calls
  send a descriptive User-Agent per their policy.
