# PoC walkthrough — the US ↔ Iran history web

This is a concrete, end-to-end proof of concept for the product's signature promise: **search
a place/actor → land on an anchor event → dig back-and-forth through what led to it and what
it caused.** It uses the curated [`seed-iran-us`](../services/agents/src/chronos_agents/seed_iran_us.py)
dataset and the real Phase-3b API. Every step below is a real endpoint + the screen it backs.

## 1. How the agents collect & show it

```bash
# 1) Tier-1 ingest — the curated US–Iran web (events + entities + sources + media + the chain)
python -m chronos_agents.run seed-iran-us
#   → {'events': 11, 'relations': 9, 'new_edges': 9}

# 2) Relation-linker — adds same-place / same-actor / precursor edges from shared entities
python -m chronos_agents.run relate

# 3) Media archival — captures the sensitive (pinned) image into the object store; the
#    encyclopedic image stays linked (ADR-0018)
python -m chronos_agents.run media-fetch
```

Each step is a registered **component** in the Admin Portal, so the operator sees the run,
its result counts, and health — `GET /admin/runs?component=agent:seed.iran-us`. In production
the same events would arrive from live feeds (RSS/Wikidata) → **enricher** tags the US/Iran
entities → **relation-linker** builds the graph; the seeder just gives us a deterministic,
fully-formed web to demonstrate the experience.

What the seed creates: **11 events** (1883 relations → 1953 coup → 1979 revolution → hostage
crisis → severed ties → Iran–Iraq War → USS Vincennes → 2015 JCPOA → 2018 withdrawal → 2020
Soleimani strike → Iran's retaliation), all tagged with **United States** + **Iran** (plus
people/places/topics), Wikipedia **sources**, three **media** items, and a curated
**causal/precursor chain**.

## 2. The end-user journey (anonymous, read-only)

### Step 1 — Search for an anchor
The user opens the app and searches "Iran" (or "Soleimani", or a date range).

```
GET /search?q=Iran
GET /search?q=Soleimani&t0=2019&t1=2021
```
→ a list of `EventRead`s. **Screen:** results drop onto the **timeline** (points/bands by
precision, colored by severity) and a list; the **map** shows markers at Tehran, Baghdad,
the Strait of Hormuz, Washington.

### Step 2 — The US ↔ Iran relationship, end to end
The defining query: *every event linking both actors*, time-ordered.

```
GET /entities?q=Iran          → find the entity id (and United States)
GET /events/by-entities?ids=<US_ID>,<IRAN_ID>
```
→ all 11 events from **1883 → 2020** in order. **Screen:** the timeline now tells the whole
relationship as one scrollable arc; zooming out buckets it, zooming in shows individual events.

### Step 3 — Open the anchor (2020 Soleimani strike)
```
GET /events/<soleimani_id>
```
→ `EventDetail`: neutral summary, **sources** (Wikipedia), **entities** (United States, Iran,
Iraq, Qasem Soleimani, Donald Trump, Baghdad — each with its role), **media** (the citizen
footage, archival `disposition: pin`, `locally_stored: true`), severity + confidence.
**Screen:** the event detail sheet with a hero image, the source list, and tappable entity chips.

### Step 4 — Dig **back**: "what led to this?"
```
GET /events/<soleimani_id>/chain?direction=back&depth=4
```
→ a `ChainResponse` of `nodes` + directed `edges`, walking the causal chain:

```jsonc
{
  "root": "<soleimani_id>", "direction": "back", "depth": 4,
  "nodes": [ /* withdrawal2018, jcpoa2015, revolution1979, coup1953, … as EventRead */ ],
  "edges": [
    { "src": "<withdrawal2018>", "dst": "<soleimani_id>", "kind": "causal",    "weight": 0.9 },
    { "src": "<jcpoa2015>",      "dst": "<withdrawal2018>","kind": "precursor", "weight": 0.9 },
    { "src": "<coup1953>",       "dst": "<revolution1979>","kind": "causal",    "weight": 0.9 }
    /* … */
  ]
}
```
**Screen:** the "dig" view renders the chain as a back-in-time spine — tap any node to recurse.

### Step 5 — Dig **forward**: "what did it cause?"
```
GET /events/<soleimani_id>/chain?direction=forward
```
→ Iran's retaliatory missile strike (and onward). **Screen:** the spine extends forward in time.

### Step 6 — Related & entity pivot
```
GET /events/<soleimani_id>/related     # one-hop neighbours across all relation kinds
GET /entities/<soleimani_person_id>/events   # every event involving the person Soleimani
```
**Screen:** a "related events" rail, and an entity page that re-pivots the timeline onto one
person/place — e.g. everything that ever involved the Strait of Hormuz.

## 3. The archival policy, visible on this case (ADR-0018)
The three media items demonstrate the full spectrum, computed from sensitivity + host:

| Event | Media origin | Sensitivity | Disposition |
|-------|--------------|-------------|-------------|
| 1883 relations (history) | Wikimedia (durable) | low | **link** (reference only) |
| 1979 revolution (politics) | Wikimedia (durable) | medium | **archive** (stored, releasable later) |
| 2020 Soleimani strike (conflict) | citizen/social footage | high | **pin** (stored, never auto-released) |

This is the point the product makes: the **most sensitive** footage — exactly what tends to
vanish under political/government/social pressure — is the one we **capture and keep locally**.

## 4. Mapping experience → component
| User sees | Endpoint | Built by |
|-----------|----------|----------|
| Search results | `/search` | events + `pg_trgm` + entity tags |
| Relationship arc | `/events/by-entities` | entity tagging (seeder / enricher) |
| Event detail | `/events/{id}` | events + sources + entities + media |
| Dig back/forward | `/events/{id}/chain` | curated chain + relation-linker |
| Related rail | `/events/{id}/related` | relation-linker |
| Operator view | `/admin/*` | registry + agent_runs + config |

## 5. Status
The seeder, endpoints, and Admin wiring are implemented and unit-tested. Seeing it **live in
the app** requires deploying this branch to the dev LXC (migrations 0002–0004 + the new
API/agents images), which is still on Phase 3a. See [infrastructure.md](infrastructure.md).
