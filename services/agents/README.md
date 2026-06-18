# chronos-agents — feed-first pipeline (Phases 1 + 3a)

Tier-1 (no LLM): pull structured feeds, normalize, publish. **Tier-2 enrichment (Phase 3a)**
adds AI summaries/entities/sub-timeline refs via the provider-agnostic LLM layer. Dedup/
geocode/relation stages arrive in Phase 3b (docs/ai-agents.md).

## Stages
```
ingest (RSS) ──► normalize ──► publish        (+ Wikidata historical seed)   [Tier-1]
enrich (LLM)  ──► summary/category/tags/impact + deep-time references          [Tier-2]
```
| Module | Role |
|--------|------|
| `normalize.py` | **Pure** raw item → `CandidateEvent` (RSS + Wikidata). BC-year + WKT parsing live here (unit-tested). |
| `publish.py` | Write a candidate via `chronos_core.repository`; simple source-URL dedup. |
| `ingest_rss.py` | Poll feeds (from Config Service) → store `ingest_items` → publish. |
| `seed_wikidata.py` | SPARQL pull of dated, geolocated historical events → populate deep time + map. |
| `enrich.py` | **Tier-2:** LLM-enrich events lacking a summary, via `chronos_core.llm` (budget-aware, auto-fallback to local). |
| `run.py` | CLI entrypoint. |

## LLM (provider-agnostic, budget-aware — ADR-0014/0015)
The enricher uses any provider via config (`llm.providers`/`llm.routing`/`llm.budget`):
vLLM/Ollama/OpenAI (OpenAI-compatible) or Claude. Default: **primary = local Ollama**, with
Claude as an optional cloud tier; set `llm.budget.max_tokens` + `primary=claude` to auto-fall
back to local once the cloud budget for the window is spent. Configure your Ollama endpoint
(`base_url` incl. `/v1`) + `model` in `llm.providers`.

## Config-driven (no redeploy to change)
Reads from the Config Service: `agents.ingest.rss.feeds`, `…enabled`,
`…max_items_per_feed`, `severity.weights`. Tune via the admin portal (Phase 3) or DB.

## Run
```sh
pip install -e ../../packages/core -e ".[dev]"
# with DATABASE_URL pointing at a migrated DB:
python -m chronos_agents.run seed-wikidata --limit 300   # historical seed (run once)
python -m chronos_agents.run ingest-rss                  # poll news feeds
python -m chronos_agents.run enrich                      # LLM-enrich a batch (Tier-2)
```
Or via the stack:
```sh
docker compose run --rm agents seed-wikidata --limit 300
docker compose run --rm agents ingest-rss
docker compose run --rm agents enrich
```

## Notes
- Idempotent: RSS deduped by `(feed, external_id)` in `ingest_items`; publish deduped by
  source URL. Re-running is safe.
- No secrets/keys needed in Phase 1 (GDELT-free; RSS + Wikidata are open). Wikidata calls
  send a descriptive User-Agent per their policy.
