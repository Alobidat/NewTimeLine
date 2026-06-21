# Event Presentation, Location Integrity & Live Search

This document specifies the next slice of work (**Phase 3c**): make every event a complete,
richly-presented article that is *always* placeable on the map and *always* connected to
related events, and let search both read existing data **and** trigger live collection that
streams new events in. It builds entirely on the existing schema (see
[data-model.md](data-model.md)) — almost nothing here needs new tables.

> **Why now.** The data model already carries title/summary/body, multi-item media,
> entities (actors/locations), the directed `event_relations` history graph, and sources.
> The gaps are (1) the **client** under-renders this, (2) **data quality** — some events
> have no `geom` so they don't highlight on the map, and many lack actors, and (3) there is
> **no bridge** from a user's search to live collection. This phase closes those gaps.

---

## 1. The event invariant: Time + Location + Actors, always

Every published event **must** carry three things; none may be left empty:

1. **Time** — `t_start`/`t_end`/`time_precision` (already always present; events can't be
   created without a time).
2. **Location** — at least one country/place the event maps to, so the map can highlight it.
3. **Actors** — at least one `actor`-role entity (person/org/country) involved.

Today the schema *permits* nulls for location and actors and the pipeline is best-effort, so
some events slip through with neither. We make the invariant real through a **resolution
cascade** (never a hard reject that silently drops events) plus **flagging** of any event
that still falls short, so it can be re-processed rather than shown broken.

### 1.1 Location-resolution cascade (ADR-0020)

When an event lacks a usable `geom`, resolve it through this ordered cascade and stop at the
first step that yields one or more locations:

1. **Existing geometry** — `events.geom` is already set (geocoder ran on `geo_label`). Done.
2. **`geo_label` → geocode** — current behaviour: Nominatim/OSM resolves the free-text place
   (`geocode.py`). Done if it returns a hit.
3. **Location-role entities** — any `event_entities` rows with `role='location'` (or
   `role='actor'` where the actor is a country/`place`) that already have `entities.geom`.
   These give **one or more** countries — exactly the multi-location case the product wants
   (e.g. a US–Iran event highlights both).
4. **Text analysis** — analyse `title` + `summary` + `body` to extract place/country mentions
   (LLM enricher pass, schema-validated), geocode those, and attach them as `location`
   entities. This is the "analyse the event info and assign one or more locations" step.
5. **Source-agency fallback (last resort)** — use the location of the **news agency / source**
   that provided the data: map `sources.domain` / `publisher` → a country (a small curated
   publisher→country table, extended over time). The event is highlighted at the reporting
   agency's country, clearly the weakest signal but never *no* location.

Each resolved location records **how** it was derived (provenance), so the UI can show a
confidence cue and operators can audit fallbacks. The cascade runs in the geocoder agent and
is re-runnable (backfill existing rows, then keep new events covered).

### 1.2 Multi-location model

An event may legitimately span several countries. We represent the **primary** location as
`events.geom` (used for the timeline/map pin and bbox queries) and the **full set** via
`location`-role entities (each with its own `geom`). The detail API returns the full set so
the map can highlight every involved country, not just one.

### 1.3 Data-integrity flagging

A lightweight check (admin-queryable, surfaced in the Admin Portal) lists events missing any
of Time/Location/Actors. The geocoder + enricher consume this worklist on each run. Nothing
is shown to end users in a broken state: an event with no resolvable location is held back
from the map layer and flagged, not rendered as an un-highlightable pin.

---

## 2. The map-highlighting fix

**Root cause (two bugs).**
1. **Data:** events with `geom IS NULL` (geocode never ran or failed) have no point and no
   country — the map can't highlight them. Fixed by §1.1's cascade + backfill.
2. **Client:** `experience_screen.dart` `_mapData()` returns empty silently when
   `_detail.geo == null`, and `country_atlas.countryAt(pt)` returns null when the point falls
   in ocean / outside a simplified polygon — so even some events *with* coordinates don't
   highlight.

**Client changes.**
- When `geo` is present but `countryAt` misses, fall back to (a) `geoLabel` → country by
  **name** (new atlas name index) and (b) nearest-country by centroid distance, so a coastal
  or disputed point still lights up a country.
- Highlight **all** countries from the event's location set (§1.2), not just one.
- When no location can be derived at all (should be rare after backfill), show an explicit
  "location unknown" affordance in the detail view rather than a dead map.

---

## 3. The article format

Every event renders in one **standard article layout**, identical in the modal sheet and the
side panel (today they diverge — `body` shows only in the panel, related links only in the
panel). The shared order:

1. **Title.**
2. **Media** — hero first, then an expandable gallery (see §4). Prefer a clip as the hero.
3. **Summary** — the neutral one-paragraph abstract.
4. **Subject / body** — the longer narrative, with **inline links** to related events where
   the body references them.
5. **Actors & place** — entity chips (actors, locations) with roles; tapping pivots to that
   entity's events.
6. **Related events (footer)** — "What led to this", "What this caused", and "Same place /
   same actors", drawn from `event_relations` via `/events/{id}/related` and `/chain`. This is
   the **second-most-important** element of an event and is always present in the footer.
7. **Sources** — citations with publisher/domain/date.

The related-event links (inline in the subject **and** in the footer) are the mechanism that
gives the user the full historical picture — what led to an event and who the actors are.

---

## 4. Rich media: multiple, expandable, clips-first

- **Multiple** images/videos per event are already supported (`event_media`, roles
  hero/gallery). The client renders them as a gallery and an **expandable fullscreen viewer**:
  swipeable carousel, pinch-to-zoom for images, fullscreen video with controls.
- **Clips over images over text** (ADR-0023): the presentation and collection both prefer
  video. We avoid text-only events — the enricher/media stage ensures **at least one image**
  and, where available, **one or more clips**. An event that would otherwise be text-only is
  flagged for media acquisition.
- Media keeps its existing archival policy (ADR-0018); nothing here changes storage.

---

## 5. Search: location / actor / keyword + live collection (ADR-0022)

### 5.1 Richer query understanding
The search bar accepts a **location** (country, city, area, … and conceptually planet),
an **event keyword**, or **actor name(s)**. The backend classifies/*fans out* the query
across: event title/body (existing), entities by name+kind (`/entities`), and place names.
Results are faceted (events vs actors vs places) so the user can pivot.

### 5.2 Search triggers live collection
A query immediately:
1. **Returns existing matches** from the DB (fast path, unchanged).
2. **Enqueues a collection job** onto the existing Redis run-queue (the `run-now` mechanism
   from Phase 3b) describing the searched location/actor/keyword.
3. An **on-demand collection agent** fetches events for that subject from the configured
   sources, runs them through the normal publish → enrich → relate → geocode → media pipeline.
4. New events **stream to the client** (reusing the Phase 3b admin real-time stream / an SSE
   channel) so the search view refreshes as results arrive — "showing 4 results, collecting
   more…".

This makes the corpus **continuously expanding**: every search both consumes and grows the
data, and our source set widens over time (§6).

---

## 6. Expanding sources

Adding an RSS feed is already config-only (`agents.ingest.rss.feeds`). This phase makes the
**source set first-class and growing**:
- A registry of source adapters (RSS, Wikidata, Wikipedia full-text, news APIs, media-rich
  archives) behind one interface, each declaring what subjects it can collect and whether it
  yields clips.
- The on-demand collection agent (§5.2) queries **all enabled** adapters for a subject, so
  adding an adapter immediately widens both background and search-driven collection.
- Media-rich sources are preferred to satisfy the clips-first policy (§4).

---

## 7. Implementation phases

| Phase | Scope | Primary surfaces |
|-------|-------|------------------|
| **A — Location integrity & map fix** *(start here; the "huge problem")* | §1 cascade + §1.2 multi-location + §1.3 flagging + §2 client fix + backfill | `geocode.py`, new `chronos_core.domain.location`, `experience_screen.dart`, `country_atlas.dart`, detail API |
| **B — Article format & rich media** | §3 unified layout + §4 expandable clips-first gallery + related-links in footer/inline | `event/*.dart`, `detail_widgets.dart` |
| **C — Rich search + live collection** | §5 query understanding + search→queue→on-demand agent → SSE stream → live client refresh | `routers/search.py`, new on-demand collection agent, `run_queue`, `top_search_bar.dart` |
| **D — Source expansion & media-richness policy** | §6 source adapter registry + §4 "no text without media" enforcement | `chronos_agents/sources/*`, enrich/media stages |

Each phase is independently shippable and demonstrable. A precedes the rest (it unblocks the
worst issue); B and C can proceed in parallel after A; D deepens C.
