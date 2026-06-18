# The "Magical Timeline" UX

This document describes the signature experience: navigating world history and live events
on a graphically rich, interactive timeline tied to a map, with sources and social layers.

## 1. The three linked surfaces

```
┌──────────────────────────────────────────────────────────────────┐
│                         GLOBE / MAP                                 │  ← where
│        events plotted as severity-sized, category-colored          │
│        markers; clusters when zoomed out                           │
├──────────────────────────────────────────────────────────────────┤
│                       EVENT DETAIL PANEL                            │  ← what
│   title · summary · severity & confidence · sources (validate) ·   │
│   entities · related events · reactions · comments                 │
├──────────────────────────────────────────────────────────────────┤
│  ◄──────────────────  THE TIMELINE  ──────────────────►           │  ← when
│  scrubbable, zoomable; events as points/bands; severity = height/  │
│  color; density "heatline"; drag to move through time              │
└──────────────────────────────────────────────────────────────────┘
```
The three are **linked**: scrubbing the timeline updates the map and detail; selecting a
map marker centers the timeline; opening related events moves both.

## 2. The timeline itself

### 2.1 Navigation
- **Scrub:** drag left/right to move through time; flick to glide with momentum.
- **Zoom:** pinch / scroll / +– to change scale — from millennia → centuries → years →
  days → hours. Zoom is *logarithmic* so both "1200 BC" and "3pm today" are reachable.
- **Jump:** a year/date input and a mini-map "overview" rail showing where event density
  is high, so users can leap to interesting periods.

### 2.2 What an event looks like on the line
- **Precise events** (`exact`/`day`) → a point/pin.
- **Spanning events** (wars, pandemics; coarse precision) → a **band** whose width is the
  duration or the precision window.
- **Severity** → encoded as marker **height + color intensity** (e.g. calm blue → urgent
  red). Color also encodes **category** (configurable: hue = category, intensity = severity).
- **Density "heatline":** when zoomed out, a continuous ribbon shows event density +
  peak severity per time bucket (from the server's precomputed buckets) so users see
  "something big happened here" before any single marker is legible.

### 2.3 Performance (how it stays smooth)
- Zoomed-out views render **server-computed buckets**, not raw events (see
  architecture.md §4.2). The client never holds millions of points.
- Custom rendering via Flutter `CustomPainter` / Impeller; only on-screen items are drawn;
  level-of-detail switches between heatline → clusters → individual markers by zoom.
- Smooth 60fps scrub: time→x is a cheap transform; data for the visible window is
  prefetched in a ring around the viewport and cached.

## 3. The map layer
- **MapLibre GL** vector map; events as markers sized by severity, colored by category.
- Clustering when zoomed out; spiderfy on dense clusters.
- Filter chips (category, severity, time-linked) apply to both map and timeline.
- An event with a region (polygon) shades the affected area.
- "Follow on map" mode animates markers appearing/pulsing as the timeline scrubs forward —
  literally watching history unfold geographically.

## 4. Event detail
- **Header:** title, time (rendered per precision: "March 11, 2011" vs "c. 1274 BC"),
  place, category.
- **Severity & confidence:** the score with an expandable **breakdown** ("impact, social,
  corroboration") so it's transparent, plus a confidence badge (verified / unverified).
- **Summary** (neutral, AI-generated, source-grounded) and optional longer narrative.
- **Sources:** list with publisher, date, and an **archived snapshot** link (never a dead
  link). Each source has community **validation controls**: corroborates / disputes /
  irrelevant, with current aggregate shown.
- **Entities:** people/orgs/places as chips → tapping pivots the timeline to that entity's
  events across history.
- **Related events:** causal/precursor/thematic/same-place/same-person — each a doorway to
  another part of the timeline (the "digging into history" promise made tactile).
- **Social:** reactions (like/dislike/important/doubt), threaded comments, share.

## 4b. Drilling into history: the sub-timeline
The main timeline only shows what sources attest, positioned at each event's **anchor
time**. But many events *talk about* deep history. Opening such an event reveals a
**sub-timeline** of its subject(s).

- **Trigger:** when a user zooms into / opens an event that has subject references, an
  expandable **"Explore the history" sub-timeline** appears within the detail view.
- **Axis shift:** the sub-timeline uses the **subject time** axis (often spanning millions
  of years), independent of the main timeline's anchor axis.
- **Worked example:** a **1956** news article about the origin of life sits at 1956 on the
  main line. Open it → a sub-timeline plots the "origin of life (~millions of years ago)"
  subject, with its precision shown as a wide band (`era`/`century` precision).
- **Recursive:** if a referenced subject is itself a canonical event (with its own
  sources and references), the user can keep diving — sub-timeline within sub-timeline —
  following history as deep as the data goes.
- **Provenance stays clear:** every sub-timeline item shows *which source* (and which
  reporting event) asserted that historical claim, and how confidently it's dated — so the
  deep-history view never loses its grounding.

## 5. Social & validation in the UI
- **Reactions** are one tap; counts feed the social component of severity.
- **Comments** are threaded; sort by top/new; report → moderation queue.
- **Source validation** is first-class: a clear, low-friction way for the community to
  vouch for or dispute each source. Reputation-weighted aggregate is visible, and a user's
  validation history builds their reputation (which in turn weights their future votes).
- **Trust signals everywhere:** confidence badges, source counts, "validated by community"
  marks — so the timeline feels credible, not just pretty.

## 6. Subscriptions, notifications & discovery
- **Follow a timeline:** any filter (topic/region/person/severity) can be saved & followed;
  new matching events notify the user (push + in-app) and appear in their feed.
- **Follow entities/events:** follow a person, place, or a developing event for updates.
- **For-you discovery:** a recommendation rail surfaces events matching the user's interest
  vector and suggests timelines/people to follow ("users interested in X also follow…").
- **Onboarding:** pick a few interests/regions → seed the interest vector → immediately get
  a populated, relevant timeline.

## 6b. Anonymous vs. signed-in (low-friction onboarding)
- **Anyone can explore:** browsing the timeline/map, opening events + sub-timelines,
  reading sources & comments, and **searching** all work **without an account**. No wall
  in front of discovery.
- **Sign in only to interact:** the moment a user taps like, comment, validate a source,
  or follow/subscribe, a **single-tap social login** sheet appears (Google / Facebook /
  Apple / …). First login auto-creates the account — **no registration form**.
- **Account linkage:** users can link multiple providers to one identity and sign in with
  any of them.
- **Context preserved:** after signing in, the user lands exactly where they were (the
  pending action — e.g. the like — completes automatically).
- *Apple requirement:* on iOS, "Sign in with Apple" is offered alongside other providers
  (App Store guideline 4.8).

## 7. Accessibility & platform fit
- Full keyboard navigation (desktop/web): arrow keys scrub, +/- zoom, Enter opens detail.
- Screen-reader labels for events (title, date, severity, place).
- Reduced-motion mode disables momentum/animation.
- Responsive layout: phones stack the three surfaces (tabs/sheets); desktop/web shows them
  side-by-side.
- Color is never the *only* severity cue (also height/size + numeric badge) for
  color-blind users.

## 8. Signature "magical" moments (the wow factor)
- **Time-lapse play:** hit play and watch markers bloom across the globe as the timeline
  advances — history animating in space and time.
- **Pivot through history:** tap a person/place and the whole timeline re-forms around them.
- **Severity heatline:** the at-a-glance ribbon that makes "when did big things happen"
  instantly readable across millennia.
- **Source-rot-proof:** every claim is one tap from an archived, community-vetted source.
