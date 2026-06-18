# Data Model

PostgreSQL + PostGIS is the system of record. This document defines the core schema.
SQL below is illustrative (Postgres dialect) — not a final migration. IDs are `uuid`
unless noted. `pgvector` provides the `vector` type for embeddings.

## 1. The temporal model (the hard part)

### 1.0 Two kinds of time: anchor time vs subject time
An event has **two** distinct temporal aspects that must never be conflated:

- **Anchor time** (`event_time`) — where the event sits on the **main timeline**. The
  main timeline is **bounded by sources**: an event appears only because a source attests
  to it. For a live earthquake the anchor ≈ now; for a datable historical event (e.g. a
  battle) the anchor is its occurrence date; for a *news report about deep-time science*
  the anchor is the **report's** date.
- **Subject time(s)** (`event_references`) — the historical period(s) an event merely
  *talks about*. These get **no main-timeline position**. Instead they form a
  **sub-timeline** revealed when the user opens the event — and recursively, a referenced
  subject can itself be a full event with its own references.

> **Worked example (yours):** A 1956 news article reports a discovery about the origin of
> life dating back millions of years.
> - On the **main timeline** we plot **one event at 1956** (the report). We do *not* invent
>   a main-timeline event "millions of years ago" — nothing reported it then.
> - The "millions of years ago" origin-of-life is stored as a **subject reference** on the
>   1956 event. When the user zooms into / opens that event, a **sub-timeline** renders the
>   referenced deep-time subject (and any related historical events linked to it).
> - If, separately, a 2010 paper also reports on the origin of life, that's its **own**
>   main-timeline event at 2010, and the sub-timeline for the subject aggregates both.

This keeps the main timeline honest ("only what sources attest") while still letting users
dive through any event into the deep history it discusses.

### 1.1 Precision
Events span from live news to antiquity, with **wildly varying precision**. We never
store "just a timestamp." Each event (and each subject reference) has a sortable instant
plus a declared precision.

```sql
CREATE TYPE time_precision AS ENUM (
  'exact',    -- to the second/minute
  'day',
  'month',
  'year',
  'decade',
  'century',
  'era'       -- "Bronze Age", anchored to an approximate year
);

-- event_time uses timestamptz; Postgres supports 4713 BC .. 294276 AD,
-- which comfortably covers recorded history. For pre-modern dates, the
-- instant is the *anchor* (e.g. midpoint of the year/century) and
-- time_precision tells the UI how to render & query it.
```

Rendering rule: the timeline draws an event as a **point** when precision is `exact`/`day`,
and as a **range/band** when coarser (the band width = the precision window or
`event_end - event_time`). Range queries always widen by the precision window so a
"year 1923" event is returned for any query overlapping 1923.

## 2. Core entities (overview)

```
users ──< follows >── (timelines | users | events)
events ──< event_sources >── sources
events ──< event_entities >── entities (person/org/place/topic)
events ──< event_relations >── events   (related-by: geo, person, causal, theme)
events ──1 geometry (PostGIS point/area)
events ──< reactions >── users          (like/unlike etc.)
events ──< comments  >── users          (threaded)
sources ──< source_votes >── users      (corroborate/dispute/irrelevant)
timelines (saved filters) ──< subscriptions >── users
users ──1 interest_vector (pgvector)    (for recommendations)
```

## 3. Tables

### 3.1 events (canonical)
```sql
CREATE TABLE events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title           text NOT NULL,
  summary         text,                       -- LLM-generated, neutral
  body            text,                       -- longer description / merged narrative
  event_time      timestamptz NOT NULL,       -- sortable anchor instant
  event_end       timestamptz,                -- NULL for instantaneous events
  time_precision  time_precision NOT NULL DEFAULT 'day',
  category        text,                        -- conflict, disaster, politics, science, culture...
  tags            text[] DEFAULT '{}',
  severity        smallint DEFAULT 0,          -- 0..100 composite, recomputed
  severity_breakdown jsonb,                    -- {impact, social, corroboration} for transparency
  confidence      smallint DEFAULT 0,          -- 0..100, from source corroboration + community
  geom            geometry(Geometry, 4326),    -- point OR polygon (areas, regions)
  geo_label       text,                        -- human place name
  embedding       vector(1024),                -- for dedup, related, recommendations
  status          text NOT NULL DEFAULT 'published', -- draft|published|merged|retracted
  merged_into     uuid REFERENCES events(id),  -- if this was deduped into another
  created_by_agent text,                       -- which agent/run produced it
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX events_time_idx       ON events (event_time);
CREATE INDEX events_time_end_idx   ON events (event_end);
CREATE INDEX events_geom_idx       ON events USING gist (geom);
CREATE INDEX events_category_idx   ON events (category);
CREATE INDEX events_tags_idx       ON events USING gin (tags);
CREATE INDEX events_embedding_idx  ON events USING hnsw (embedding vector_cosine_ops);
CREATE INDEX events_severity_idx   ON events (severity DESC);
```

### 3.2 sources & source archival
```sql
CREATE TABLE sources (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  url           text NOT NULL,
  domain        text NOT NULL,
  title         text,
  publisher     text,
  published_at  timestamptz,
  snapshot_key  text,                  -- object-store key of archived HTML/screenshot
  content_hash  text,                  -- dedup identical source fetches
  quality_score smallint DEFAULT 50,   -- 0..100, from domain reputation + community
  kind          text,                  -- news, primary_doc, dataset, encyclopedia, social
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (content_hash)
);

CREATE TABLE event_sources (             -- many-to-many: an event cited by N sources
  event_id   uuid REFERENCES events(id) ON DELETE CASCADE,
  source_id  uuid REFERENCES sources(id) ON DELETE CASCADE,
  relation   text DEFAULT 'reports',     -- reports|corroborates|disputes|background
  added_by   text,                       -- agent run or user id
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, source_id)
);
```
The **count of distinct sources** on an event feeds the corroboration component of severity.

### 3.3 entities (people, orgs, places, topics) + linking
```sql
CREATE TABLE entities (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind        text NOT NULL,            -- person | org | place | topic
  name        text NOT NULL,
  external_id text,                     -- e.g. Wikidata QID for canonical identity
  geom        geometry(Point,4326),     -- for places
  embedding   vector(1024),
  meta        jsonb,
  UNIQUE (kind, external_id)
);

CREATE TABLE event_entities (
  event_id  uuid REFERENCES events(id) ON DELETE CASCADE,
  entity_id uuid REFERENCES entities(id) ON DELETE CASCADE,
  role      text,                        -- actor, location, subject, affected...
  PRIMARY KEY (event_id, entity_id, role)
);
```
Entities power the "related via persons / geography" navigation and historical digs:
e.g., from a current event tagged with a person/place, find all past events sharing them.

### 3.4 event relations (the "history graph")
```sql
CREATE TABLE event_relations (
  src_event uuid REFERENCES events(id) ON DELETE CASCADE,
  dst_event uuid REFERENCES events(id) ON DELETE CASCADE,
  kind      text NOT NULL,    -- causal | precursor | thematic | same-place | same-person | sequel
  weight    real DEFAULT 1.0, -- strength, from embedding similarity + shared entities
  PRIMARY KEY (src_event, dst_event, kind)
);
```

### 3.4b event_references (the sub-timeline / subject time)
Captures the deep-time / historical **subjects** an event discusses (see §1.0). These power
the sub-timeline shown when a user opens an event. A reference may link to a canonical
event (recursive sub-timelines) or stand alone as a derived subject.
```sql
CREATE TABLE event_references (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id         uuid REFERENCES events(id) ON DELETE CASCADE,  -- the reporting event (e.g. 1956 article)
  label            text NOT NULL,            -- "origin of life", "Bronze Age collapse"
  subject_time     timestamptz NOT NULL,     -- when the referenced subject occurred (anchor of the sub-timeline item)
  subject_end      timestamptz,              -- for spans
  subject_precision time_precision NOT NULL DEFAULT 'era',
  subject_geom     geometry(Geometry,4326),  -- where, if known
  subject_event_id uuid REFERENCES events(id), -- OPTIONAL: link to a canonical event → recursive sub-timeline
  detail           text,                      -- short narrative of the referenced subject
  confidence       smallint DEFAULT 50,       -- how confidently the source dates the subject
  extracted_by     text,                      -- agent run
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX event_references_event_idx   ON event_references (event_id);
CREATE INDEX event_references_subject_idx ON event_references (subject_time);
CREATE INDEX event_references_geom_idx    ON event_references USING gist (subject_geom);
```
The enricher (and tier-3 dig) extract these subject references from source text. The
sub-timeline query for an opened event = its `event_references` ordered by `subject_time`,
plus (recursively) the references of any linked `subject_event_id`.

### 3.5 users, social graph, reputation
```sql
CREATE TABLE users (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  handle          text UNIQUE NOT NULL,
  display_name    text,
  email           text UNIQUE,         -- primary email (from a linked identity); nullable
  -- auth identities live in user_identities (account linkage across social providers)
  reputation      integer DEFAULT 0,   -- earns from validated contributions
  interest_vector vector(1024),        -- rolling profile for recommendations
  prefs           jsonb DEFAULT '{}',  -- notif settings, privacy opt-ins
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Account linkage: one user, many linked social identities (Google, Facebook, Apple…).
-- Lets a user sign in with any linked provider and merge accounts. Minimal-friction signup:
-- first social login auto-creates the users row; no separate registration form required.
CREATE TABLE user_identities (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid REFERENCES users(id) ON DELETE CASCADE,
  provider      text NOT NULL,           -- google | facebook | apple | email | twitter | ...
  provider_sub  text NOT NULL,           -- subject id from that provider (OIDC 'sub')
  email         text,                    -- provider-asserted email (may be a relay, e.g. Apple)
  linked_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_sub)
);
CREATE INDEX user_identities_user_idx ON user_identities (user_id);

CREATE TABLE follows (                  -- generic follow: user follows entity/timeline/user
  user_id     uuid REFERENCES users(id) ON DELETE CASCADE,
  target_type text NOT NULL,            -- 'timeline' | 'user' | 'entity' | 'event'
  target_id   uuid NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, target_type, target_id)
);
```

### 3.6 reactions & comments
```sql
CREATE TABLE reactions (
  user_id  uuid REFERENCES users(id) ON DELETE CASCADE,
  event_id uuid REFERENCES events(id) ON DELETE CASCADE,
  kind     text NOT NULL,               -- like | dislike | important | doubt
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, event_id, kind)
);

CREATE TABLE comments (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id   uuid REFERENCES events(id) ON DELETE CASCADE,
  user_id    uuid REFERENCES users(id) ON DELETE CASCADE,
  parent_id  uuid REFERENCES comments(id) ON DELETE CASCADE, -- threading
  body       text NOT NULL,
  score      integer DEFAULT 0,         -- up/down aggregate
  status     text DEFAULT 'visible',    -- visible|flagged|removed
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX comments_event_idx ON comments (event_id, created_at);
```

### 3.7 source validation (community trust)
```sql
CREATE TABLE source_votes (
  user_id   uuid REFERENCES users(id) ON DELETE CASCADE,
  event_id  uuid REFERENCES events(id) ON DELETE CASCADE,
  source_id uuid REFERENCES sources(id) ON DELETE CASCADE,
  verdict   text NOT NULL,              -- corroborates | disputes | irrelevant
  weight    real DEFAULT 1.0,           -- = f(user.reputation) at vote time
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, event_id, source_id)
);
```
Aggregated, reputation-weighted verdicts adjust event `confidence` and source `quality_score`.

### 3.8 timelines (saved filters) & subscriptions
```sql
CREATE TABLE timelines (                -- a named, shareable filter
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id    uuid REFERENCES users(id) ON DELETE CASCADE,
  name        text NOT NULL,
  filter      jsonb NOT NULL,           -- {categories, tags, bbox, entity_ids, time_range, min_severity}
  is_public   boolean DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE subscriptions (
  user_id     uuid REFERENCES users(id) ON DELETE CASCADE,
  timeline_id uuid REFERENCES timelines(id) ON DELETE CASCADE,
  notify      boolean DEFAULT true,
  PRIMARY KEY (user_id, timeline_id)
);
```
When the publisher emits a new event, the notification service matches it against
`timelines.filter` to fan out to subscribers (see ai-agents.md & architecture.md §4.5).

### 3.9 notifications & ingestion bookkeeping
```sql
CREATE TABLE notifications (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id   uuid REFERENCES users(id) ON DELETE CASCADE,
  kind      text NOT NULL,              -- new_event | comment_reply | source_validated | recommended
  payload   jsonb NOT NULL,
  read_at   timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_user_idx ON notifications (user_id, created_at DESC);

CREATE TABLE ingest_items (             -- raw feed items, pre-normalization (audit + replay)
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  feed        text NOT NULL,
  external_id text,
  raw         jsonb NOT NULL,
  fetched_at  timestamptz NOT NULL DEFAULT now(),
  state       text NOT NULL DEFAULT 'new', -- new|normalized|deduped|published|discarded
  UNIQUE (feed, external_id)
);
```

## 4. Key query patterns

| Need | Query shape |
|------|-------------|
| Timeline window (zoomed in) | `WHERE event_time && [t0,t1] AND geom && bbox AND <filters> ORDER BY event_time` |
| Timeline buckets (zoomed out) | aggregate counts + `max(severity)` per time bucket (precomputed → Redis) |
| Map within viewport | PostGIS `ST_Intersects(geom, bbox)` + severity for sizing |
| Related events | `event_relations` join + `embedding <=> $1` nearest neighbors |
| "Same person/place across history" | via `event_entities` shared entity → events ordered by `event_time` |
| Dedup candidate | `embedding <=> $candidate ORDER BY ... LIMIT k` then LLM adjudication |
| Subscription match | evaluate `timelines.filter` against new event (category/tag/bbox/entity/severity) |
| Recommendations | `events.embedding <=> users.interest_vector` minus already-seen |

## 5. Notes & decisions for later
- **Bitemporal?** We track `created_at`/`updated_at` (transaction time) and `event_time`
  (valid time). Full bitemporal history (audit of every field change) can be added via a
  `events_history` table if regulators/historians require it. Deferred.
- **Vector dim (1024):** placeholder; match the chosen embedding model. Keep configurable.
- **Partitioning:** at scale, partition `events` by time range and `comments`/`reactions`
  by event hash. Not needed for MVP.
- **Graph workload:** the history graph is modest; Postgres recursive CTEs suffice. A
  dedicated graph DB is only warranted if relation traversal becomes a bottleneck.
