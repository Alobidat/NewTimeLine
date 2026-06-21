# `event/` — the standard event article

Renders a single event as **one** article layout (ADR-0021), identical in the modal sheet
and the inline side panel, plus a clips-first expandable media gallery (ADR-0023). Backend
and data model are unchanged — this module is pure presentation over the existing detail,
`/related`, and `/chain` APIs.

## Public interface

| Symbol | File | What it does |
|--------|------|--------------|
| `EventArticle` | `event_article.dart` | The shared layout. Used by **both** hosts. Fetches its own `/related`. |
| `RelatedFooter` | `event_article.dart` | The always-present related-events footer (3 groups). |
| `buildBodySpans(...)` | `event_article.dart` | Pure helper: turns related-event titles named in the body into tappable inline links. Unit-tested. |
| `showEventDetail` / `showEventDetailById` | `event_detail_sheet.dart` | Open the article in a draggable modal sheet. |
| `DetailPanel` | `detail_panel.dart` | Inline panel host (close button + in-place related pivot). |
| `MediaGallery` | `detail_widgets.dart` | Clips-first hero + thumbnail strip → fullscreen viewer. |
| `orderMediaClipsFirst(...)` | `detail_widgets.dart` | Pure helper: video before image, hero-role first. Unit-tested. |
| `Section`, `Pill`, `SeverityBadge`, `entityIcon` | `detail_widgets.dart` | Small shared chrome. |

## The layout (order, ADR-0021 §3)

1. **Title** (+ optional `headerTrailing` slot — the panel's close button)
2. **Media** — clip-preferred hero + expandable gallery
3. *(optional `footerExtra` slot — the sheet's "Dig the history" button)*
4. **Summary**
5. **Subject / body** — with **inline links** to related events the body names
6. **Actors & place** — entity chips (tap pivots to the entity's events)
7. **Related events footer** — *always present*; "What led to this" / "What this caused" /
   "Same place / same actors" from `/related` (kinds: causal → led/caused by `direction`;
   `same-place`/`same-actor` → same context)
8. **Sources**
9. **Sub-timeline references** (deep-history subjects, ADR-0005)

The related-event links (inline **and** the footer) are the product's second-most-important
element — they give the full historical picture and are always shown.

## Rich media (ADR-0023)

`MediaGallery` shows a large hero (a video clip is preferred when present) and a thumbnail
strip. Tapping any tile opens a fullscreen, swipeable viewer:

- **Images** pinch/pan-zoom via `InteractiveViewer` (no `photo_view` dependency).
- **Videos** play fullscreen with a play/pause overlay + scrub bar (`video_player`).
- Archival (`disposition == 'pin'`) badges and captions are preserved.

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
and the `video_player` package.
