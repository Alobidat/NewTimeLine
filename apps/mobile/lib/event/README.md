# `event/` — the standard event article

Renders a single event as **one** article layout (ADR-0021), identical in the modal sheet
and the inline side panel, with a **media-first** presentation (ADR-0024): clips lead, then
images, then prose. Backend and data model are unchanged — this module is pure presentation
over the existing detail, `/related`, and `/chain` APIs.

## Public interface

| Symbol | File | What it does |
|--------|------|--------------|
| `EventArticle` | `event_article.dart` | The shared layout. Used by **both** hosts. Fetches its own `/related`. |
| `RelatedFooter` | `event_article.dart` | The always-present related-events footer (3 groups). |
| `buildBodySpans(...)` | `event_article.dart` | Pure helper: turns related-event titles named in the body into tappable inline links. Unit-tested. |
| `bodyNeedsExpander(...)` / `kBodyCollapseChars` | `event_article.dart` | Pure helper: whether a body is long enough to collapse behind "Read more". Unit-tested. |
| `showEventDetail` / `showEventDetailById` | `event_detail_sheet.dart` | Open the article in a draggable modal sheet. |
| `DetailPanel` | `detail_panel.dart` | Inline panel host (close button + in-place related pivot). |
| `MediaGallery` | `media_gallery.dart` | Media-first hero (clip preview) + gallery strip with "+N" → fullscreen viewer. |
| `orderMediaClipsFirst(...)` / `isShowableMedia(...)` | `media_gallery.dart` | Pure helpers: clips-first ordering; image/video filter. Unit-tested. |
| `MediaFrame`, `MediaThumb`, `ShimmerBox` | `media_tiles.dart` | Tile frame, decoding poster (blur-up/shimmer + graceful error), shimmer placeholder. Re-exported by `media_gallery.dart`. |
| `openMediaViewer(...)`, `FullscreenViewer` | `media_viewer.dart` | Swipeable fullscreen carousel: pinch-zoom images, sound + controls video. |
| `Section`, `Pill`, `SeverityBadge`, `entityIcon` | `detail_widgets.dart` | Small shared chrome. |

`detail_widgets.dart` re-exports the media symbols (`MediaGallery`, `orderMediaClipsFirst`,
`isShowableMedia`, `openMediaViewer`, `FullscreenViewer`) so existing callers that imported
them from there keep working.

## The layout (order, ADR-0021 §3 + ADR-0024)

1. **Title** (+ optional `headerTrailing` slot — the panel's close button)
2. **Meta chips** — time / place / category / severity / source-count, compact
3. **Media** — a prominent clip-first hero + a visible gallery strip with a "+N" affordance
4. *(optional `footerExtra` slot — the sheet's "Dig the history" button)*
5. **Summary** — the short lead, given a touch more weight than body prose
6. **Subject / body** — with **inline links** to named related events, **collapsed behind
   "Read more"** when long (`> kBodyCollapseChars`)
7. **Actors & place** — entity chips (tap pivots to the entity's events)
8. **Related events footer** — *always present*; "What led to this" / "What this caused" /
   "Same place / same actors" from `/related`
9. **Sources**
10. **Sub-timeline references** (deep-history subjects, ADR-0005)

The related-event links (inline **and** the footer) are the product's second-most-important
element — they give the full historical picture and are always shown.

## Media-forward presentation (ADR-0024 / ADR-0023)

`MediaGallery` leads with motion and pictures, treating prose as support:

- **Hero — clips first.** When a video clip exists it becomes the hero as a **muted,
  looping autoplay *preview*** (no controls, autoplays where the platform allows it). A tap
  opens the fullscreen viewer with **sound + full controls**. With no clip the hero is the
  best image; with neither, the block renders nothing (the article degrades to text).
- **More media, larger, above the fold.** A generous hero (height capped on wide screens so
  one clip can't eat the whole fold) plus a visible thumbnail strip. Beyond a few tiles the
  remainder collapse behind a **"+N" tile** that opens the fullscreen carousel at the first
  hidden item.
- **Never a broken tile.** Images show a **shimmer/blur-up placeholder** while decoding
  (`ShimmerBox`) and a graceful glyph on error; a clip that fails to initialise falls back
  to its poster. Aspect ratios are respected (`FittedBox`/`AspectRatio`).

The fullscreen viewer (`media_viewer.dart`) is a swipeable carousel: **images** pinch/pan-
zoom via `InteractiveViewer` (no `photo_view` dependency); **videos** play with sound and a
play/pause overlay + scrub bar (`video_player`). Only the visible page's clip plays.

## Hosts are thin wrappers

`event_detail_sheet.dart` and `detail_panel.dart` only own host-specific chrome and pass
slots/callbacks into `EventArticle`:

- Sheet → draggable sheet frame + "Dig the history" button (`footerExtra`); related events
  open in a fresh sheet (article default when `onSelectRelated` is null); entity chips push
  a `ResultsScreen`.
- Panel → close button (`headerTrailing`) + in-place related pivot (`onSelectRelated`).

## Depends on

`../api/client.dart`, `../api/models.dart`, `../domain/time_format.dart`,
`../theme/severity.dart`, `../dig/dig_screen.dart`, `../search/results_list.dart`,
and the `video_player` package. No new dependencies were added for the media-forward pass.
