# Source adapters

A first-class, growing registry of upstream sources behind one interface
(event-presentation.md §6). Adding a source = adding an adapter + its
`agents.sources.<id>.*` config specs; the on-demand collection agent then queries it
automatically, widening both background and search-driven collection.

## Interface (`base.py`)

- `SubjectQuery(keyword, location, actor)` — the searched subject (event-presentation §5.1).
  `.text()` gives the combined query string.
- `Capabilities(yields_clips, media_rich, handles_keyword/location/actor)` — what an adapter
  can do; drives collector ordering (clips-first, ADR-0023).
- `SourceAdapter` — abstract: `id`, `title`, `capabilities`, `can_handle(subject)`,
  `async collect(subject, *, limit) -> list[CandidateEvent]`. Adapters return the same
  `normalize.CandidateEvent`/`CandidateMedia` every ingestor produces, so candidates flow
  through the unchanged `publish.publish_candidate` → enrich → relate → geocode → media path.

## Adapters

| id | source | media-rich | clips |
|----|--------|:---------:|:-----:|
| `wikipedia` | Wikipedia full-text (`list=search`) + lead image + WebM clip | yes | yes |
| `wikidata`  | dated/geolocated SPARQL events, label-filtered | no | no |
| `rss`       | configured RSS feeds, title/summary match | partial | no |

`wikimedia.py` holds the shared Wikipedia REST helpers (`wiki_image`, `wiki_video`,
`best_webm`) reused by the Wikipedia adapter **and** the US–Iran PoC seeder.

## Registry + collector

- `registry.all_adapters / enabled_adapters / get_adapter` — `enabled_adapters` filters by
  `agents.sources.<id>.enabled` (default True).
- `collect.run_collect(subject)` — the on-demand agent (event-presentation §5.2). Queries
  clip-bearing / media-rich adapters first, then publishes each candidate. Phase C enqueues
  `collect` jobs (subject in job args) that this handles.
