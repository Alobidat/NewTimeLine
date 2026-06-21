# Accounts, Social Graph & the Video Feed (Phase 4 + rec slice)

This is the engagement layer: **real accounts** (social login, mandatory email verification,
agreement acceptance, GDPR self-service), a **user-to-user social graph** (follow), full
**interactions** (comment/react/promote on events, links, sources, actors), **user-uploaded
video events**, an **activity-driven interest profile**, and a **TikTok-style video-first
client** (For You / Following / Discover with swipe navigation). It turns the `get_actor`
identity stub (ADR-0025) into real auth and pulls the Phase-5 recommendation slice forward so
we can learn what to tune from real usage.

Builds on: ADR-0007 (social login decided), the interaction substrate (ADR-0025: comments/
reactions/source_votes + user links), the media-forward UI (ADR-0024), and the
`event_relations` graph + `entities`. Tables `users`/`user_identities`/`follows`/
`interest_vector` were designed in [data-model.md](data-model.md) §3.5/§3.8 — we implement them.

---

## 1. Accounts & auth (ADR-0026)

**Minimal, social-first.** No password/registration form: the user picks a provider, authorizes,
and is in. We support **all major providers and let the user choose**: Google, Apple, Facebook,
X (Twitter), and we keep the set **config-driven** (a provider registry mirroring the LLM
provider pattern) so adding one is config, not code.

- **Flow:** OAuth2/OIDC authorization-code (PKCE). Callback verifies the provider token, then
  **first login auto-provisions** a `users` row and links the identity in `user_identities`;
  signing in later with another linked provider resolves to the same user (**account linkage**).
  The API issues its own **session token** (signed JWT) thereafter; `get_actor` (ADR-0025) is
  re-implemented to resolve it (anonymous still allowed for read).
- **Email verification is REQUIRED to interact** (comment/react/promote/upload/follow). Providers
  that assert a verified email (Google/Apple) satisfy it immediately; otherwise (e.g. X may not
  return email) we collect + **verify via emailed link/code** before write access. Reads stay open.
- **Agreement acceptance:** on first login the user must accept the **Terms / acceptable-use /
  privacy** (a versioned document); acceptance (user, version, timestamp) is recorded and
  re-prompted when the version changes. Interaction is gated on a current acceptance.
- **GDPR self-service (available from day one):**
  - **Delete my account** — irreversibly removes the user and **all their data** (identities,
    comments, reactions, votes, follows, uploaded media/events authored, activity, interest
    vector). Cascades + an explicit purge of object-store uploads.
  - **Download my data** — exports everything we hold about the user as a portable archive
    (JSON + their uploaded media manifest) on demand.
- **Config/secrets:** per-provider client id/secret + scopes, JWT signing secret, SMTP (for
  verification mail), current agreement version. Secrets via env/Settings (like `admin_token`);
  non-secret toggles via the Config Service (ADR-0019).

## 2. Social graph & interactions (ADR-0025 extended)

- **Follow** users and entities (people/orgs/places/topics) and events — `follows` (designed in
  data-model §3.5). Follower/following lists; counts. **User-to-user following is first-class** —
  it powers the **Following** feed.
- **Interactions everywhere.** Already built for events (comments threaded, like/dislike/
  important/doubt, source votes). Extend **promote/demote (vote up/down)** to: **events**,
  **links** (`event_relations`), **sources**, and **actors/entities**. Promotions feed ranking
  (and later the social-severity + confidence/quality signals).
- **Activity log.** Every meaningful action (view, watch-through, like, comment, promote, follow,
  upload, dwell) is recorded to drive the interest profile (§4) and analytics for tuning.

## 3. User-generated video events (ADR-0029)

MVP upload, metadata-complete by construction (ties to the ADR-0020 invariant + ADR-0024 clips):
- Authed, email-verified users **upload a clip**; the client requires **time, location, actors,
  and link(s) to other events** before submit (the same fields every event must have).
- Server stores the binary in the object store (existing media pipeline / archival policy
  ADR-0018), creates the `media` (kind=video, hero) + a new `event` (or attaches to an existing
  one), tags entities (actors/location), geocodes (ADR-0020 cascade), and records the user links.
- **Moderation = flag/queue stub** now (status `pending`/`visible`/`removed`); transcode +
  LLM-assisted moderation are a later pass.

## 4. Interest profile & recommendations (ADR-0028 — Phase-5 slice)

Heuristic + interest profile (no ML training yet):
- **Interest profile** built from the activity log: weighted counts over the **entities,
  categories, places, and authors** the user engages with (and decayed over time).
- **For You ranking** = blend of *recency*, *popularity* (votes/views/watch-through),
  *media-richness* (clips first, ADR-0024), and *interest match* (overlap with the profile),
  minus already-seen. Cheap to compute; the activity log is the substrate for a later
  embedding/ML pass (the `interest_vector`/`embedding` columns already exist).
- **Feed endpoints:** `For You` (ranked), `Following` (events from followed users/entities,
  reverse-chron + light ranking), `Discover` (trending/serendipity). All return **video-first**
  events.

## 5. TikTok-style client (ADR-0027)

Three tabs — **For You / Following / Discover** — over a **vertical full-screen video feed**:
- **Swipe up / down** → next / previous event video in the current feed (autoplay, loop, muted-
  until-tapped; preloads neighbours).
- **Swipe right** → the event's **graph/timeline web**: a node-link view on the time axis (past →
  future) of related/causal events; selecting a node shows the videos at that **location / time /
  actors** (reuses the existing map/atlas + `event_relations` + `/related`/`/chain`).
- **Swipe left** → the **next related event in the current timeline** (a guided lateral walk).
- **Overlay controls** (right rail + bottom, TikTok-style): react/emotion, comment (opens the
  threaded sheet), promote/vote, follow author, share, and an **info affordance** revealing the
  event **metadata** (time/location/actors/sources/links). Authoring (upload) entry + account/
  profile screens. Sign-in is prompted on first interaction, preserving the pending action.

## 6. Implementation waves

| Wave | Agent | Scope | Surfaces |
|------|-------|-------|----------|
| **1** | **A** (backend) | §1 accounts/auth/GDPR + migration 0006 (`users`,`user_identities`,`user_agreements`) + provider registry + JWT sessions + email verify + replace `get_actor` | `packages/core`, `db/migrations`, `services/api` auth/account |
| **1** | **F** (Flutter) | §5 TikTok feed shell: 3 tabs, vertical video feed, swipe up/down·left·right, overlay rail, info sheet — against the documented feed/interaction contract | `apps/mobile/lib/feed`, `shell`, `main.dart` |
| **2** | **B** (backend) | §2 follow + promote(events/links/sources/actors) + activity log + §3 upload + §4 interest profile + feed/rec API; migration 0007 (`follows`,`activity_log`,promote targets) | `services/api`, `packages/core`, `services/agents` |
| **2** | **G** (Flutter) | §1 auth UI: provider-choice login, agreement consent, email-verify, account settings (**delete account**, **download data**), sign-in-on-interaction | `apps/mobile/lib/auth`, `account` |
| **3** | **IU2** | Wire the feed/overlay/upload UI to the real feed+rec+upload+follow+promote APIs; profile screen; polish | `apps/mobile` |

Sequencing: Wave 1 lays the auth foundation (everything depends on real users) and the feed UI
shell in parallel (disjoint: backend vs Flutter). Wave 2 builds social/feed/rec/upload on the
real `users` table + the auth UI. Wave 3 integrates. Each wave: verify (pytest/flutter) → commit
→ auto-deploy.
