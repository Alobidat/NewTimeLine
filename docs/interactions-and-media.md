# Media-forward Presentation & Interaction Foundations

This document specifies the next slice (**Phase 3d**): make the event experience **media-first**
(clips > images > text) and **tidy**, and lay the **foundations for user interaction** —
threaded comments, reactions (like/dislike/important/doubt), source/event votes, and
**user-created links between events** — building on the tables already designed in
[data-model.md](data-model.md) §3.5–3.7. Auth itself stays in Phase 4; here we build the
data + API + UI so interaction is ready to switch on.

---

## 1. Media-forward presentation (ADR-0024)

**Principle: users give more time to a clip than an image, and more to an image than text.**
So the event article leads with motion and pictures, and treats prose as support.

- **Hierarchy clips > images > text.** Hero is a **video clip** whenever one exists (muted
  autoplay-preview/loop where the platform allows; tap → fullscreen with sound + controls),
  else the best image. The gallery shows *more* media, larger, above the fold.
- **Tidy the layout.** Reduce text dominance: summary first (short), body collapsed behind
  "Read more", metadata as compact chips. Generous media; consistent spacing; one clear visual
  rhythm shared by the modal sheet and the side panel (the `EventArticle` from Phase 3c-B).
- **Quality matters.** Prefer higher-resolution images and real clips; show a tasteful
  placeholder/blur-up while loading; never show a broken tile. Degrade gracefully to image,
  then to text, but flag text-only events for media acquisition (ties to ADR-0023 / `media_gap`).
- **Quantity.** Surface all attached media (hero + gallery + inline), with a clear "+N" affordance
  into the fullscreen carousel.

This is a presentation + media-quality pass on top of Phase 3c-B/D — no schema change for the
UI side; the media-quality side improves what the collectors fetch (higher-res variants, clips).

## 2. Interaction foundations (ADR-0025)

The data model already designs `reactions`, `comments`, and `source_votes` (data-model.md
§3.5–3.7) and `event_relations.added_by` records a **user** as a link author. We implement
these now so the product can build engagement; **writes are gated behind an identity stub**
today (anonymous/dev actor) and swap to real OIDC sessions in Phase 4 with no API change.

### 2.1 Threaded comments
- New `comments` table/model (id, event_id, user_id, **parent_id** for threading, body, score,
  status, timestamps) + migration. API: list (tree/paged), create reply, edit/delete own,
  soft-moderate (status). LLM-assisted flagging is deferred to Phase 4.

### 2.2 Reactions (like / dislike / important / doubt)
- New `reactions` table/model (user_id, event_id, kind, PK on the triple → one of each kind per
  user). API: toggle a reaction, read aggregate counts (+ the caller's own set). Aggregates feed
  the *social* component of severity later.

### 2.3 Votes (source & event credibility)
- `source_votes` (corroborate / dispute / irrelevant), reputation-weighted later. API: cast vote,
  read aggregates. Wired to adjust `confidence` / `quality_score` in a later pass.

### 2.4 User-created event links
- Let a user assert a relation between two events (`event_relations` with `added_by=<user>` and a
  `kind` from the existing set, default `thematic`). API: create/remove a user link; these render
  in the Phase 3c-B related-events footer alongside agent-derived links, tagged "added by a user".

### 2.5 Identity stub (bridge to Phase 4)
- A single `get_actor` dependency returns the current user id. Today it resolves an anonymous/dev
  actor (configurable), so interaction is testable end-to-end; Phase 4 replaces its body with the
  OIDC session lookup. No router or schema changes when auth lands.

## 3. Implementation phases

| Phase | Scope | Surfaces |
|-------|-------|----------|
| **M — Media-forward UI** | §1 presentation: clip-hero autoplay, larger/more media, tidy layout, blur-up/placeholders | `apps/mobile/lib/event/**`, `apps/mobile/lib/shell/**` |
| **I — Interaction API foundations** | §2.1–2.5 models + migration 0005 + schemas + repository + routers + identity stub | `packages/core/.../models,schemas`, `db/migrations`, `services/api/.../routers` |
| **MQ — Media quality/collection** | §1 quality: higher-res images + real clips, prefer clips in collectors | `services/agents/.../sources`, `media_fetch.py` |
| **IU — Interaction UI** | comment threads, reaction bar, vote affordances, "link this event" — wired to I's API | `apps/mobile/lib/event/**`, new interaction widgets |

Wave 1 (parallel, disjoint): **M** (Flutter) + **I** (backend API). Wave 2: **MQ** (backend) +
**IU** (Flutter, needs I's API + M's layout). Auth stays stubbed until Phase 4.
