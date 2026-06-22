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

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../auth/interaction_gate.dart';
import '../state/auth_state.dart';
import 'event_graph_view.dart';
import 'feed_clip_player.dart';
import 'feed_info_sheet.dart';
import 'feed_source.dart';
import 'overlay_rail.dart';
import 'prefetch.dart';
import 'share.dart';

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

  /// Event ids the user has saved this session (drives the filled bookmark icon). Seeded
  /// optimistically on toggle — we don't pre-fetch each item's saved state to keep the feed
  /// request-light, so a previously-saved clip shows unfilled until the user taps it.
  final Set<String> _bookmarked = {};

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
    _dragDy = 0;
    if (next) {
      _moveFeed(1); // swipe up → next event in the feed
    } else if (prev) {
      _moveFeed(-1); // swipe down → previous event in the feed
    }
  }

  /// Web only: a swipe detected on the `<video>` element itself (which is the topmost DOM
  /// element over the clip and so receives the touches before Flutter — see [FeedClipPlayer]).
  /// Classifies by dominant axis + travel/velocity, mirroring the native gesture thresholds.
  void _onWebSwipe(double dx, double dy, double vx, double vy) {
    if (!mounted || _items.isEmpty) return;
    final size = MediaQuery.sizeOf(context);
    if (dx.abs() > dy.abs()) {
      final hThreshold = size.width * _dragFraction;
      if (dx > hThreshold || vx > _flingVelocity) {
        _walkTimeline(forward: true); // swipe right → next in timeline
      } else if (dx < -hThreshold || vx < -_flingVelocity) {
        _walkTimeline(forward: false); // swipe left → previous in timeline
      }
    } else {
      final vThreshold = size.height * _dragFraction;
      if (dy < -vThreshold || vy < -_flingVelocity) {
        _moveFeed(1); // swipe up → next event in the feed
      } else if (dy > vThreshold || vy > _flingVelocity) {
        _moveFeed(-1); // swipe down → previous event in the feed
      }
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
    showReactionSheet(context, widget.api, item.event.id);
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

  /// Comment opens the same info sheet (it contains the threaded discussion); kept a
  /// distinct entry point so the rail button reads "Comment".
  void _comment(FeedItem item) => _info(item);

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
            // Web: the clip element is the swipe surface (it sits above Flutter's gesture layer
            // in the DOM). Image heroes are Flutter-painted, so swipes over them fall through to
            // the GestureDetector below — this callback is only consumed for <video> clips.
            onSwipe: _onWebSwipe,
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
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onVerticalDragStart: (_) => _dragDy = 0,
            onVerticalDragUpdate: (d) => _dragDy += d.delta.dy,
            onVerticalDragEnd: _onVerticalDragEnd,
            onHorizontalDragEnd: (d) {
              final v = d.primaryVelocity ?? 0;
              if (v > _flingVelocity) {
                _walkTimeline(forward: true); // right → next in timeline
              } else if (v < -_flingVelocity) {
                _walkTimeline(forward: false); // left → previous in timeline
              }
            },
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
          ),
        ),
        // TEMPORARY on-screen D-pad mirroring the swipe actions, so we can agree the mapping
        // before trusting the gestures. Up/Down = next/previous event in the feed; Right/Left =
        // next/previous event in THIS event's timeline (disabled + greyed when there's none in
        // that direction). Remove once the gestures are confirmed.
        Positioned(
          left: 8,
          bottom: 150,
          child: _SwipeDpad(
            onUp: canUp ? () => _moveFeed(1) : null,
            onDown: canDown ? () => _moveFeed(-1) : null,
            onLeft: canPrev ? () => _walkTimeline(forward: false) : null,
            onRight: canNext ? () => _walkTimeline(forward: true) : null,
          ),
        ),
      ],
    );
  }
}

/// A temporary directional pad that fires the same actions as the feed's swipes, so the gesture
/// mapping can be agreed on-screen before the swipe directions are finalised. Labelled so each
/// button states what it does.
class _SwipeDpad extends StatelessWidget {
  const _SwipeDpad({
    required this.onUp,
    required this.onDown,
    required this.onLeft,
    required this.onRight,
  });

  /// A null callback marks that direction as unavailable — the button greys out and ignores
  /// taps (e.g. Left/Right when the event has no earlier/later event in its timeline).
  final VoidCallback? onUp, onDown, onLeft, onRight;

  @override
  Widget build(BuildContext context) {
    Widget btn(String key, IconData icon, String label, VoidCallback? onTap) {
      final enabled = onTap != null;
      final color = enabled ? Colors.white : Colors.white30;
      return Padding(
        padding: const EdgeInsets.all(2),
        child: Material(
          color: Colors.black.withValues(alpha: enabled ? 0.5 : 0.25),
          shape: const StadiumBorder(),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            key: Key('dpad-$key'),
            onTap: onTap, // null → non-interactive (disabled)
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(icon, color: color, size: 16),
                  const SizedBox(width: 4),
                  Text(label, style: TextStyle(color: color, fontSize: 11)),
                ],
              ),
            ),
          ),
        ),
      );
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        btn('up', Icons.keyboard_arrow_up, 'Up · next event', onUp),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            btn('left', Icons.keyboard_arrow_left, 'Left · prev in timeline',
                onLeft),
            btn('right', Icons.keyboard_arrow_right, 'Right · next in timeline',
                onRight),
          ],
        ),
        btn('down', Icons.keyboard_arrow_down, 'Down · prev event', onDown),
      ],
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
