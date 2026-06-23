/// The vertical full-screen video feed for ONE tab (ADR-0027 §5). A vertical [PageView]:
///   • swipe **up / down** → next / previous event video,
///   • each page autoplays (loop, muted) while visible and pauses off-screen,
///   • the current page ±1 are kept buffered (preloaded) so a swipe starts instantly,
///   • the rest dispose their controllers (bounded memory — see [FeedClipPlayer]).
///
/// Lateral navigation (the other two gestures, social-and-feed §5):
///   • swipe **right** → pushes the event's graph/timeline web ([EventGraphView]);
///     selecting a node opens that event in a fresh nested feed.
///   • swipe **left**  → fetches the next *forward* related event ([ApiClient.related],
///     direction='forward') and appends + advances to it — a guided walk along the timeline,
///     staying immersive.
///
/// The list grows by paging the [FeedSource]; reaching the end fetches the next page. The
/// overlay actions (promote/react/comment/follow) are wired to the live interaction API and
/// each write is gated through `ensureCanInteract` (IU2): an anonymous tap walks the user
/// through sign-in → consent → verify, then resumes the pending action.
library;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../auth/interaction_gate.dart';
import '../event/comments_page.dart';
import '../state/auth_state.dart';
import 'event_graph_view.dart';
import 'feed_clip_player.dart';
import 'feed_info_sheet.dart';
import 'feed_source.dart';
import 'overlay_rail.dart';
import 'prefetch.dart';
import 'share.dart';
import 'web_video.dart';

class VideoFeed extends StatefulWidget {
  const VideoFeed({
    super.key,
    required this.api,
    required this.auth,
    required this.source,
    required this.tab,
    this.onAddVideo,
  });

  final ApiClient api;
  final AuthState auth;
  final FeedSource source;
  final FeedTab tab;

  /// Opens the "upload a clip" flow — wired to a button in the bottom bar. Null in nested feeds
  /// that don't carry the home's upload entry point (the button is hidden then).
  final VoidCallback? onAddVideo;

  @override
  State<VideoFeed> createState() => _VideoFeedState();
}

class _VideoFeedState extends State<VideoFeed>
    with AutomaticKeepAliveClientMixin {
  final List<FeedItem> _items = [];

  /// Accumulated vertical drag distance for the in-progress swipe (logical px; negative = the
  /// finger moved up = toward the next clip). Reset on each drag start / page change.
  double _dragDy = 0;

  /// TEMPORARY on-screen gesture monitor (top HUD) — shows what Flutter actually receives so we
  /// can diagnose the "centre swipe does nothing" report on a real device. Remove once resolved.
  String _dbg = 'swipe anywhere';
  int _gestureN = 0;

  /// Event ids the user has saved this session (drives the filled bookmark icon). Seeded
  /// optimistically on toggle — we don't pre-fetch each item's saved state to keep the feed
  /// request-light, so a previously-saved clip shows unfilled until the user taps it.
  final Set<String> _bookmarked = {};

  // Per-event engagement counts shown on the action rail, loaded lazily for the on-screen
  // event and refreshed after the user acts on it.
  final Map<String, EventStats> _stats = {};
  final Set<String> _statsLoading = {};

  String? _cursor;
  bool _loading = false;
  bool _exhausted = false;
  Object? _error;

  // ── Two independent navigation axes ───────────────────────────────────────────────────
  //
  // VERTICAL (up/down) walks the ranked feed [_items]; [_current] is the row. HORIZONTAL
  // (left/right) walks the CURRENT row event's own timeline, held in [_lateral] with cursor
  // [_lateralIdx] — a per-row chain seeded with the row event itself. The two never interfere:
  // a left/right walk only touches [_lateral], and any up/down move resets [_lateral] to the new
  // row event, so "next/previous video" up/down is always the same regardless of lateral walking.
  int _current = 0;
  List<FeedItem> _lateral = [];
  int _lateralIdx = 0;

  /// The event actually on screen — the current point of the lateral walk (the row event itself
  /// until the user swipes left/right).
  FeedItem get _displayed => (_lateral.isEmpty)
      ? _items[_current.clamp(0, _items.length - 1)]
      : _lateral[_lateralIdx.clamp(0, _lateral.length - 1)];

  /// Whether the *displayed* event has an earlier / later related event — drives the Left/Right
  /// button enabled state. Null while the one-hop lookup is in flight. [_relCheckedFor] guards
  /// against re-probing the same event and against stale async results.
  bool? _hasPrevEvent;
  bool? _hasNextEvent;
  String? _relCheckedFor;

  /// Seed the lateral chain with the current row event (called on first load and every up/down
  /// move) so horizontal navigation always starts from the feed event.
  void _resetLateral() {
    _lateral = _items.isEmpty
        ? []
        : [_items[_current.clamp(0, _items.length - 1)]];
    _lateralIdx = 0;
  }

  @override
  bool get wantKeepAlive => true; // keep each tab's scroll position + controllers.

  @override
  void initState() {
    super.initState();
    _loadMore();
  }

  // ── Vertical paging ───────────────────────────────────────────────────────────────────
  //
  // The clip and the overlay are both pinned (rendered once, source-swapped on settle), so the
  // feed never actually *scrolls* — paging is just swapping which clip is active. We therefore
  // drive it directly from a single gesture surface instead of a (transparent) PageView: a
  // PageView only pages once its viewport is physically dragged past a fraction or hard-flung,
  // and because nothing visibly moves, a gentle swipe snapped back and felt dead (the bug the
  // user kept hitting). Here a swipe pages on a *small* distance OR a *gentle* fling, and
  // up/down are perfectly symmetric — no scroll physics to fight.

  /// px/s; a flick at least this fast pages in its direction even without much travel.
  static const double _flingVelocity = 220;

  /// Fraction of the screen height a fling-less drag must cover to page (gentle but deliberate).
  static const double _dragFraction = 0.06;

  void _onVerticalDragEnd(DragEndDetails d) {
    final v = d.primaryVelocity ?? 0; // negative = upward fling = next
    final threshold = MediaQuery.sizeOf(context).height * _dragFraction;
    final next = v < -_flingVelocity || _dragDy < -threshold;
    final prev = v > _flingVelocity || _dragDy > threshold;
    setState(() {
      _gestureN++;
      _dbg = 'V-DRAG dy=${_dragDy.round()} v=${v.round()} '
          '→ ${next ? "NEXT" : prev ? "PREV" : "none"}';
    });
    _dragDy = 0;
    if (next) {
      _moveFeed(1); // swipe up → next event in the feed
    } else if (prev) {
      _moveFeed(-1); // swipe down → previous event in the feed
    }
  }

  /// VERTICAL move: step the feed by [delta] (clamped) and snap back to the main column by
  /// resetting the lateral chain — so up/down always lands on the next/previous *feed* event,
  /// independent of any left/right walking the user did on the previous row.
  void _moveFeed(int delta) {
    if (_items.isEmpty) return;
    final target = (_current + delta).clamp(0, _items.length - 1);
    final atEdge = target == _current;
    // Nothing to do only if we're already at the row event AND can't move further.
    if (atEdge && _lateralIdx == 0) return;
    setState(() {
      _current = target;
      _resetLateral();
    });
    _prefetchUpcoming();
    _refreshRelatedIndicator();
    if (target >= _items.length - 2) _loadMore();
  }

  /// Probe the *displayed* event for earlier/later related events (one hop, both directions) so
  /// the Left/Right buttons can show whether a lateral move will go anywhere. Deduped per event
  /// and race-guarded: a late response is dropped if the user has since moved elsewhere.
  Future<void> _refreshRelatedIndicator() async {
    if (_items.isEmpty) return;
    final id = _displayed.id;
    if (_relCheckedFor == id) return;
    _relCheckedFor = id;
    setState(() {
      _hasPrevEvent = null;
      _hasNextEvent = null;
    });
    List<RelatedEvent> rel;
    try {
      rel = await widget.api.related(id, direction: 'both');
    } catch (_) {
      rel = const [];
    }
    if (!mounted) return;
    // Ignore if the user has moved on while we were fetching.
    if (_displayed.id != id) return;
    setState(() {
      _hasNextEvent = rel.any((r) => r.direction == 'forward');
      _hasPrevEvent = rel.any((r) => r.direction == 'back');
    });
  }

  Future<void> _loadMore() async {
    if (_loading || _exhausted) return;
    setState(() => _loading = true);
    try {
      final pageResult =
          await widget.source.page(widget.tab, cursor: _cursor);
      if (!mounted) return;
      setState(() {
        _items.addAll(pageResult.items);
        _cursor = pageResult.nextCursor;
        _exhausted = pageResult.nextCursor == null;
        _error = null;
      });
      if (_lateral.isEmpty && _items.isNotEmpty) _resetLateral(); // seed the first row
      _prefetchUpcoming();
      _refreshRelatedIndicator(); // first page → probe the opening clip's neighbours
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Warm the next two clips (FR-1.3) so a swipe lands on an already-buffered video. The
  /// visible player still renders one clip at a time (platform-view constraint); this only
  /// pre-fetches the upcoming urls into cache. No-op off the web (see [prefetchClips]).
  void _prefetchUpcoming() {
    final urls = <String>[];
    for (var k = 1; k <= 2; k++) {
      final j = _current + k;
      if (j < _items.length) {
        final id = _items[j].heroMediaId;
        if (id != null) urls.add(widget.api.mediaUrl(id));
      }
    }
    prefetchClips(urls);
  }

  // ── Lateral navigation ────────────────────────────────────────────────────────────────

  /// Swipe right: open the graph/timeline web for [item]. Selecting a node opens that event
  /// in a fresh single-item nested feed so the immersive model is preserved.
  void _openGraph(FeedItem item) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => EventGraphView(
          api: widget.api,
          root: item.event,
          onOpenEvent: (e) {
            Navigator.of(context).pop(); // leave the graph
            _openEventFeed(e);
          },
        ),
      ),
    );
  }

  /// Open a nested immersive feed seeded with a single event (used by graph-node taps and
  /// the related-event pivot). It reuses the full [VideoFeed] page UI via a [_SeededSource]
  /// so the user keeps swiping up/down/left/right there too.
  void _openEventFeed(EventRead seed) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => Scaffold(
          backgroundColor: Colors.black,
          body: VideoFeed(
            api: widget.api,
            auth: widget.auth,
            source: SeededFeedSource(widget.source, seed),
            tab: widget.tab,
            onAddVideo: widget.onAddVideo,
          ),
        ),
      ),
    );
  }

  /// HORIZONTAL move along the current row event's own timeline. [forward] → the next event
  /// (swipe right), else the previous one (swipe left). This only touches the lateral chain
  /// [_lateral]/[_lateralIdx] — never [_items]/[_current] — so up/down stays anchored to the
  /// feed. Already-walked steps are revisited from the chain; new ones are fetched one hop and
  /// appended/prepended. A no-op (with a toast) when the timeline ends in that direction.
  Future<void> _walkTimeline({required bool forward}) async {
    if (_lateral.isEmpty) return;
    // Re-use the chain if we've already walked this way.
    if (forward && _lateralIdx + 1 < _lateral.length) {
      setState(() => _lateralIdx++);
      _refreshRelatedIndicator();
      return;
    }
    if (!forward && _lateralIdx > 0) {
      setState(() => _lateralIdx--);
      _refreshRelatedIndicator();
      return;
    }
    // Otherwise fetch the next/previous hop from the *displayed* event.
    final from = _displayed.event;
    List<RelatedEvent> related;
    try {
      related = await widget.api.related(
        from.id,
        direction: forward ? 'forward' : 'back', // API: ^(back|forward|both)$
      );
    } catch (_) {
      related = const [];
    }
    if (!mounted || _displayed.event.id != from.id) return;
    final next = related.isNotEmpty ? related.first : null;
    if (next == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(forward
              ? 'No later event in this timeline.'
              : 'No earlier event in this timeline.'),
        ),
      );
      return;
    }
    setState(() {
      // Carry the related event's hero media so the lateral card shows real media, not a glyph.
      final item = FeedItem(
        event: next.event,
        heroMediaId: next.heroMediaId,
        heroIsClip: next.heroIsClip,
      );
      if (forward) {
        _lateral.add(item);
        _lateralIdx = _lateral.length - 1;
      } else {
        _lateral.insert(0, item);
        _lateralIdx = 0;
      }
    });
    _refreshRelatedIndicator();
  }

  // ── Overlay actions ───────────────────────────────────────────────────────────────────
  //
  // Every write goes through `ensureCanInteract` first (ADR-0026): an anonymous tap walks
  // sign-in → consent → verify and only then resumes the action. Reads (info) never gate.

  Future<void> _react(FeedItem item) async {
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    if (!mounted) return;
    await showReactionSheet(context, widget.api, item.event.id);
    _reloadStats(item.event.id); // the reaction count may have changed
  }

  void _info(FeedItem item) => showFeedInfoSheet(
        context,
        widget.api,
        item.event.id,
        onSelectRelated: (id) {
          Navigator.of(context).maybePop();
          // Pivot the feed to the chosen related event in a fresh nested feed.
          widget.api.event(id).then((d) {
            if (mounted) _openEventFeed(d);
          }).catchError((_) {});
        },
      );

  /// Comment opens the full discussion page: event/media header + threaded comments with
  /// per-comment reactions and author profiles. Reads are open; writes gate on tap.
  void _comment(FeedItem item) {
    Navigator.of(context)
        .push(
          MaterialPageRoute<void>(
            builder: (_) => CommentsPage(
              api: widget.api,
              auth: widget.auth,
              event: item.event,
            ),
          ),
        )
        .then((_) => _reloadStats(item.event.id)); // comment count may have changed
  }

  Future<void> _promote(FeedItem item, bool up) async {
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    try {
      // Toggle: a second tap of the same direction clears the vote (value 0).
      final res = await widget.api.promote('event', item.event.id, up ? 1 : -1);
      _toast(res.mine > 0
          ? 'Promoted'
          : res.mine < 0
              ? 'Demoted'
              : 'Vote cleared');
      _reloadStats(item.event.id);
    } catch (_) {
      _toast('Could not record your vote.');
    }
  }

  Future<void> _follow(FeedItem item) async {
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    try {
      // Follow the event itself — the "Following" tab then surfaces its related/updated
      // events. (Following the *creator* is the separate "Creator" button, [_followCreator].)
      await widget.api.follow('event', item.event.id);
      _toast('Following this event');
      _reloadStats(item.event.id);
    } catch (_) {
      _toast('Could not follow.');
    }
  }

  /// Follow the clip's creator (only offered when the event carries an author id).
  Future<void> _followCreator(FeedItem item) async {
    final author = item.event.authorId;
    if (author == null) return;
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    try {
      await widget.api.follow('user', author);
      _toast('Following the creator');
    } catch (_) {
      _toast('Could not follow the creator.');
    }
  }

  /// Load the engagement counts for [eventId] once (cached). Safe to call from build — it
  /// no-ops when the counts are cached or already loading.
  void _ensureStats(String eventId) {
    if (_stats.containsKey(eventId) || _statsLoading.contains(eventId)) return;
    _statsLoading.add(eventId);
    widget.api.eventStats(eventId).then((s) {
      if (mounted) setState(() => _stats[eventId] = s);
    }).catchError((_) {}).whenComplete(() => _statsLoading.remove(eventId));
  }

  /// Refresh the counts for [eventId] after the user acts on it (react/promote/follow/save/
  /// comment), so the rail numbers reflect the change.
  void _reloadStats(String eventId) {
    _stats.remove(eventId);
    _ensureStats(eventId);
  }

  /// Toggle this clip in the user's saved collection. Optimistic: flip the local set + icon,
  /// then reconcile with the server, rolling back on error.
  Future<void> _bookmark(FeedItem item) async {
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    final id = item.id;
    final want = !_bookmarked.contains(id);
    setState(() => want ? _bookmarked.add(id) : _bookmarked.remove(id));
    try {
      want ? await widget.api.bookmark(id) : await widget.api.unbookmark(id);
      _toast(want ? 'Saved' : 'Removed from saved');
      _reloadStats(item.event.id);
    } catch (_) {
      if (mounted) {
        setState(() => want ? _bookmarked.remove(id) : _bookmarked.add(id));
      }
      _toast('Could not update saved.');
    }
  }

  /// Share this clip: opens the share sheet (OS share sheet on the web, with a Copy-link
  /// fallback) for a deep link back onto this deployment (see `share.dart`). A read, so it
  /// never gates on sign-in.
  void _share(FeedItem item) => showShareSheet(context, item.event);

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg)));
  }

  // ── Build ─────────────────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    super.build(context); // keep-alive
    if (_items.isEmpty) {
      if (_error != null) {
        return _Message(
          icon: Icons.cloud_off,
          text: 'Could not load the feed.',
          action: ('Retry', _loadMore),
        );
      }
      if (_loading) {
        return const Center(child: CircularProgressIndicator());
      }
      return const _Message(
        icon: Icons.movie_filter_outlined,
        text: 'No videos in this feed yet.',
      );
    }

    // Both the clip AND the controls are pinned (rendered ONCE), so neither moves while the
    // user pages — only the transparent gesture pages of the PageView actually scroll:
    //   • the looping clip fills the screen BEHIND the PageView (a video_player platform view
    //     placed *inside* a PageView mis-positions on CanvasKit web), source-swapped on settle;
    //   • the scrim + action rail + caption are pinned ON TOP, bound to the current clip, so
    //     the buttons stay put between videos (their transparent areas let vertical drags fall
    //     through to the PageView and horizontal flings reach the per-page gesture surface).
    // The displayed event is the current point of the lateral walk (the feed row event until the
    // user swipes left/right). Up/down operate on the feed index behind it; left/right on the
    // lateral chain — see the two-axes note on the state fields.
    final current = _displayed;
    _ensureStats(current.event.id); // lazy-load the action-rail counts for the on-screen event
    final clipUrl = current.heroMediaId != null
        ? widget.api.mediaUrl(current.heroMediaId!)
        : null;
    // Left/Right availability: a lateral move is possible if the chain already has a neighbour
    // that way, or the displayed event has a related event in that direction.
    final canPrev = _lateralIdx > 0 || _hasPrevEvent != false;
    final canNext =
        _lateralIdx + 1 < _lateral.length || _hasNextEvent != false;
    // Up/Down availability: down only when there's an earlier feed event; up while more remain.
    final canUp = _current < _items.length - 1 || !_exhausted;
    final canDown = _current > 0;
    return Stack(
      fit: StackFit.expand,
      children: [
        Positioned.fill(
          child: FeedClipPlayer(
            key: ValueKey('clip-${widget.tab.slug}-${current.id}'),
            url: clipUrl,
            active: true,
            isClip: current.heroIsClip,
            posterUrl: null,
          ),
        ),
        // The single transparent gesture surface that drives ALL four feed gestures. One
        // GestureDetector (not a PageView, not per-page detectors) so vertical and horizontal
        // recognizers are disambiguated cleanly by Flutter's arena — the dominant axis wins and
        // they never fight. Vertical → next/previous clip (pinned player swapped on settle);
        // horizontal → next (right) / previous (left) event in the timeline. Translucent so taps
        // over the rail's transparent middle still reach the buttons above (higher in the stack).
        Positioned.fill(
          key: const Key('feed-gestures'),
          // TEMP: Listener records EVERY raw pointer that reaches Flutter (regardless of gesture
          // recognition), so the HUD reveals whether a centre swipe is reaching Flutter at all.
          child: Listener(
            behavior: HitTestBehavior.translucent,
            onPointerDown: (e) => setState(() =>
                _dbg = 'DOWN ${e.position.dx.round()},${e.position.dy.round()}'),
            onPointerMove: (e) => setState(() =>
                _dbg = 'MOVE dy=${e.delta.dy.round()} @${e.position.dy.round()}'),
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onVerticalDragStart: (_) => _dragDy = 0,
              onVerticalDragUpdate: (d) => _dragDy += d.delta.dy,
              onVerticalDragEnd: _onVerticalDragEnd,
              onHorizontalDragEnd: (d) {
                final v = d.primaryVelocity ?? 0;
                setState(() => _dbg = 'H-DRAG v=${v.round()}');
                if (v > _flingVelocity) {
                  _walkTimeline(forward: true); // right → next in timeline
                } else if (v < -_flingVelocity) {
                  _walkTimeline(forward: false); // left → previous in timeline
                }
              },
            ),
          ),
        ),
        // Pinned bottom scrim so the caption stays legible over bright clips (childless →
        // transparent to gestures, so paging underneath is unaffected).
        const Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          height: 220,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
                colors: [Colors.black54, Colors.transparent],
              ),
            ),
          ),
        ),
        // Pinned action rail + caption for the current clip — fixed in place across swipes.
        // Positioned.fill so the rail's internally-Positioned buttons/caption resolve against
        // the full screen (a bare Stack of only-Positioned children collapses to a top strip).
        Positioned.fill(
          child: OverlayRail(
            api: widget.api,
            event: current.event,
            bookmarked: _bookmarked.contains(current.id),
            onReact: () => _react(current),
            onComment: () => _comment(current),
            onInfo: () => _info(current),
            onPromote: (up) => _promote(current, up),
            onFollow: () => _follow(current),
            onFollowCreator:
                current.event.authorId != null ? () => _followCreator(current) : null,
            onBookmark: () => _bookmark(current),
            onShare: () => _share(current),
            onOpenGraph: () => _openGraph(current),
            onAddVideo: widget.onAddVideo,
            stats: _stats[current.event.id],
          ),
        ),
        // Web-only sound toggle. The web feed autoplays muted (browser policy); this is the
        // user gesture that unmutes it, and the preference then carries to every clip. (Native
        // clips toggle by tapping the clip — see FeedClipPlayer.) Top-left, clear of the rail.
        if (kIsWeb)
          Positioned(
            top: 56,
            left: 12,
            child: SafeArea(
              child: ValueListenableBuilder<bool>(
                valueListenable: feedMuted,
                builder: (context, muted, _) => Material(
                  color: Colors.black.withValues(alpha: 0.45),
                  shape: const CircleBorder(),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    key: const Key('feed-mute-toggle'),
                    onTap: () => setFeedMuted(!muted),
                    child: Padding(
                      padding: const EdgeInsets.all(9),
                      child: Icon(
                        muted ? Icons.volume_off : Icons.volume_up,
                        color: Colors.white,
                        size: 22,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        // TEMPORARY on-screen D-pad mirroring the swipe actions, so we can agree the mapping
        // before trusting the gestures. Up/Down = next/previous event in the feed; Right/Left =
        // next/previous event in THIS event's timeline (greyed when there's none in that
        // direction). The primary navigation control — one bottom-centre pad you swipe in any
        // of the four directions; full-screen swipes still work too.
        Positioned(
          left: 0,
          right: 0,
          bottom: 120,
          child: Center(
            child: _SwipeNub(
              onUp: canUp ? () => _moveFeed(1) : null,
              onDown: canDown ? () => _moveFeed(-1) : null,
              onLeft: canPrev ? () => _walkTimeline(forward: false) : null,
              onRight: canNext ? () => _walkTimeline(forward: true) : null,
            ),
          ),
        ),
        // TEMP: gesture monitor HUD. Shows the last raw pointer + the last drag Flutter
        // recognised, so we can see whether a centre swipe reaches Flutter at all.
        Positioned(
          top: 90,
          left: 12,
          right: 12,
          child: IgnorePointer(
            child: Center(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  'monitor #$_gestureN  ·  $_dbg',
                  style: const TextStyle(color: Colors.greenAccent, fontSize: 12),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// The feed's primary navigation control: a single bottom-centre pad. **Swipe** it in any of
/// the four directions — or **tap an arrow** — to fire that action. Up/Down page the feed
/// (next/previous event); Left/Right walk THIS event's timeline. While you drag, a knob follows
/// your finger and the target chevron lights up, then the knob springs back (live feedback).
/// Edge chevrons grey out when there's no neighbour that way (that direction is ignored). The
/// pad is opaque, so gestures starting on it route here; swipes anywhere else still page the
/// feed normally.
class _SwipeNub extends StatefulWidget {
  const _SwipeNub({
    required this.onUp,
    required this.onDown,
    required this.onLeft,
    required this.onRight,
  });

  final VoidCallback? onUp, onDown, onLeft, onRight;

  @override
  State<_SwipeNub> createState() => _SwipeNubState();
}

class _SwipeNubState extends State<_SwipeNub>
    with SingleTickerProviderStateMixin {
  static const double _diameter = 104;
  static const double _maxR = 26; // how far the knob may travel from centre
  static const double _threshold = 12; // min travel to register a direction
  static const double _deadzone = 14; // centre press that picks no direction
  static const Offset _centre = Offset(_diameter / 2, _diameter / 2);

  late final AnimationController _spring = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 260),
  )..addListener(() {
      final t = Curves.elasticOut.transform(_spring.value);
      setState(() => _knob = Offset.lerp(_from, Offset.zero, t)!);
    });

  Offset _knob = Offset.zero; // live knob offset from centre
  Offset _from = Offset.zero; // knob offset when a spring-back began
  String? _active; // direction currently highlighted

  Offset _clamp(Offset v) {
    final d = v.distance;
    return d <= _maxR ? v : v * (_maxR / d);
  }

  /// The dominant direction of [v], or null if it's within the centre deadzone.
  String? _dirOf(Offset v) {
    if (v.dx.abs() < _threshold && v.dy.abs() < _threshold) return null;
    if (v.dx.abs() > v.dy.abs()) return v.dx > 0 ? 'right' : 'left';
    return v.dy < 0 ? 'up' : 'down';
  }

  VoidCallback? _cbFor(String? d) => switch (d) {
        'up' => widget.onUp,
        'down' => widget.onDown,
        'left' => widget.onLeft,
        'right' => widget.onRight,
        _ => null,
      };

  void _fire(Offset v) => _cbFor(_dirOf(v))?.call();

  void _springBack() {
    _from = _knob;
    setState(() => _active = null);
    _spring.forward(from: 0);
  }

  @override
  void dispose() {
    _spring.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Widget chevron(String dir, Alignment a, IconData icon, bool enabled) {
      final hot = _active == dir && enabled;
      return Align(
        alignment: a,
        child: Padding(
          padding: const EdgeInsets.all(2),
          child: Icon(
            icon,
            size: hot ? 30 : 26,
            color: enabled
                ? (hot ? Colors.white : Colors.white70)
                : Colors.white24,
          ),
        ),
      );
    }

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) => _spring.stop(),
      onTapUp: (d) {
        final v = d.localPosition - _centre;
        if (v.distance < _deadzone) return; // centre press → no direction
        setState(() {
          _knob = _clamp(v);
          _active = _dirOf(v);
        });
        _fire(v);
        _springBack();
      },
      onPanDown: (_) => _spring.stop(),
      onPanStart: (_) => setState(() => _knob = Offset.zero),
      onPanUpdate: (d) => setState(() {
        _knob = _clamp(_knob + d.delta);
        _active = _dirOf(_knob);
      }),
      onPanEnd: (_) {
        _fire(_knob);
        _springBack();
      },
      child: Container(
        key: const Key('swipe-nub'),
        width: _diameter,
        height: _diameter,
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.42),
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white24),
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            chevron('up', Alignment.topCenter, Icons.keyboard_arrow_up, widget.onUp != null),
            chevron('down', Alignment.bottomCenter, Icons.keyboard_arrow_down, widget.onDown != null),
            chevron('left', Alignment.centerLeft, Icons.keyboard_arrow_left, widget.onLeft != null),
            chevron('right', Alignment.centerRight, Icons.keyboard_arrow_right, widget.onRight != null),
            // The knob: follows the finger during a drag/tap, then springs back to centre.
            Transform.translate(
              offset: _knob,
              child: Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.22),
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white54),
                ),
                child: const Icon(Icons.open_with, size: 24, color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.icon, required this.text, this.action});
  final IconData icon;
  final String text;
  final (String, VoidCallback)? action;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 64, color: Colors.white38),
          const SizedBox(height: 12),
          Text(text, style: const TextStyle(color: Colors.white70)),
          if (action != null) ...[
            const SizedBox(height: 12),
            FilledButton(onPressed: action!.$2, child: Text(action!.$1)),
          ],
        ],
      ),
    );
  }
}
