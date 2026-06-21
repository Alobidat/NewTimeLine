# `feed/` — the TikTok-style video feed shell (Phase 4-F, ADR-0027)

The app **home**: three tabs (For You / Following / Discover), each a vertical full-screen
video feed, with the four-direction swipe model and the right-rail overlay
(social-and-feed.md §5).

## Files

| File | Responsibility |
|------|----------------|
| `feed_home.dart` | App home scaffold: the 3 floating tabs + `TabBarView`; overflow menu → classic map/timeline (`ExperienceScreen`). Owns the shared `ApiClient` + `FeedSource`. |
| `video_feed.dart` | One tab's vertical `PageView`: paging, active/preload tracking, and **all** lateral-nav + overlay-action wiring. |
| `feed_item.dart` | One page: clip + overlay + the horizontal-swipe gesture layer. |
| `feed_clip_player.dart` | Muted, looping, cover-fit clip player. Lazy-init, disposes off-window. Tap = mute toggle. |
| `overlay_rail.dart` | The right rail (react/comment/promote/follow/share/info) + bottom caption + swipe hints. `showReactionSheet`. |
| `event_graph_view.dart` | Swipe-right graph/timeline web: related events laid on a horizontal time axis (`CustomPaint` connectors). Bridges to `ExperienceScreen`. |
| `feed_info_sheet.dart` | The info/metadata + discussion sheet — reuses the shared `EventArticle` (no reimplementation). |
| `feed_source.dart` | The feed data contract (`FeedItem`/`FeedPage`/`FeedTab`) + the temporary shim over existing endpoints. |

## Swipe model

| Gesture | Effect |
|---------|--------|
| **Up / down** | Next / previous event video (vertical `PageView`). |
| **Right** | Open the event's **graph/timeline web** (`EventGraphView`); tap a node → nested feed for it. |
| **Left** | Advance to the next **forward-related** event (`related(direction:'forward')`) — guided lateral walk, stays immersive. |

## Autoplay / preload

- The visible page (`active`) autoplays, loops, muted. Tap toggles mute (and resumes play).
- Immediate neighbours (`±1`) are `preload`ed (buffered, not playing) so a swipe starts
  instantly.
- All other pages dispose their `VideoPlayerController` → only ~3 controllers live at once
  (bounded memory). Off-screen pages pause **and rewind**.

## Overlay actions — wired vs stubbed

| Action | Status |
|--------|--------|
| React | **Live** — `toggleReaction` via the shared `ReactionBar` (reaction sheet). |
| Comment | **Live** — opens the shared threaded `CommentsSection` (in the info sheet). |
| Info | **Live** — full `EventArticle` (time/location/actors/sources/links). |
| Promote / demote | **Live with fallback** — calls `promoteEvent` (not live yet → caught), then falls back to the live reaction substrate (`like`/`dislike`). |
| Follow author | **Stub** — `followAuthor` (no route yet, no author id on `EventRead`); snackbar on failure. TODO(phase-4-B). |
| Share | **Stub** — snackbar (no `share_plus` dep). TODO(IU2). |

## FeedSource contract & the swap

`FeedSource.page(tab, cursor, limit) → FeedPage{items:[FeedItem{event, heroMediaId}],
nextCursor}`.

Today it is a **shim** over `/timeline` (falling back to `/search`) returning a single page
(no real ranking, no hero clip ids yet). When the rec API lands (social-and-feed §4):

1. Replace `FeedSource.page`'s body with a single `GET /feed/{tab.slug}?cursor=…&limit=…`
   returning `{items:[{event, hero_media_id, score}], next_cursor}`.
2. Delete `_fallbackEvents`.
3. `FeedItem`/`FeedPage`/`FeedTab` and the whole UI stay unchanged.

Two thin client methods were added in `api/client.dart` against the documented contract and
are tolerated-on-failure until live: `followAuthor`, `promoteEvent`.
