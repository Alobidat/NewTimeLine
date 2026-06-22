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
  int _current = 0;

  /// Whether the current event has an earlier / later related event (drives the bottom
  /// prev/next indicator and tells the user a left/right swipe will land somewhere). Null while
  /// the one-hop related lookup for the current event is still in flight. [_relCheckedFor] guards
  /// against re-fetching for an event we've already probed and against stale async results.
  bool? _hasPrevEvent;
  bool? _hasNextEvent;
  String? _relCheckedFor;

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
      _goTo(_current + 1);
    } else if (prev) {
      _goTo(_current - 1);
    }
  }

  /// Web only: a swipe detected on the `<video>` element itself (which is the topmost DOM
  /// element over the clip and so receives the touches before Flutter — see [FeedClipPlayer]).
  /// Classifies by dominant axis + travel/velocity, mirroring the native gesture thresholds.
  void _onWebSwipe(double dx, double dy, double vx, double vy) {
    if (!mounted || _items.isEmpty) return;
    final current = _items[_current.clamp(0, _items.length - 1)];
    final size = MediaQuery.sizeOf(context);
    if (dx.abs() > dy.abs()) {
      final hThreshold = size.width * _dragFraction;
      if (dx > hThreshold || vx > _flingVelocity) {
        _walkTimeline(current, forward: true); // swipe right → next in timeline
      } else if (dx < -hThreshold || vx < -_flingVelocity) {
        _walkTimeline(current, forward: false); // swipe left → previous in timeline
      }
    } else {
      final vThreshold = size.height * _dragFraction;
      if (dy < -vThreshold || vy < -_flingVelocity) {
        _goTo(_current + 1); // swipe up → next clip
      } else if (dy > vThreshold || vy > _flingVelocity) {
        _goTo(_current - 1); // swipe down → previous clip
      }
    }
  }

  /// Activate clip [i] (clamped). Swaps the pinned player + overlay to it and warms the next
  /// clips; near the end it pages the source. A no-op when already there.
  void _goTo(int i) {
    final target = i.clamp(0, _items.length - 1);
    if (target == _current) return;
    setState(() => _current = target);
    _prefetchUpcoming();
    _refreshRelatedIndicator();
    if (target >= _items.length - 2) _loadMore();
  }

  /// Probe the current event for earlier/later related events (one hop, both directions) so the
  /// bottom indicator can show whether a left/right swipe will go anywhere. Deduped per event and
  /// race-guarded: a late response is dropped if the user has since moved to another clip.
  Future<void> _refreshRelatedIndicator() async {
    if (_items.isEmpty) return;
    final id = _items[_current.clamp(0, _items.length - 1)].id;
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
    // Ignore if the user has paged away while we were fetching.
    if (_items[_current.clamp(0, _items.length - 1)].id != id) return;
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

  /// Lateral walk along the event's own timeline: [forward] → the next event (swipe right,
  /// left-to-right), else the previous one (swipe left, right-to-left). Fetches the one-hop
  /// related event in that direction, appends it to the feed (if new) and advances to it.
  Future<void> _walkTimeline(FeedItem item, {required bool forward}) async {
    List<RelatedEvent> related;
    try {
      related = await widget.api.related(
        item.event.id,
        direction: forward ? 'forward' : 'back', // API: ^(back|forward|both)$
      );
    } catch (_) {
      related = const [];
    }
    if (!mounted) return;
    final next = related.isNotEmpty ? related.first.event : null;
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
    var idx = _items.indexWhere((i) => i.id == next.id);
    if (idx < 0) {
      setState(() => _items.add(FeedItem(event: next)));
      idx = _items.length - 1;
    }
    _goTo(idx);
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
    final current = _items[_current.clamp(0, _items.length - 1)];
    final clipUrl = current.heroMediaId != null
        ? widget.api.mediaUrl(current.heroMediaId!)
        : null;
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
                _walkTimeline(current, forward: true); // right → next in timeline
              } else if (v < -_flingVelocity) {
                _walkTimeline(current, forward: false); // left → previous in timeline
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
            onUp: () => _goTo(_current + 1),
            onDown: _current > 0 ? () => _goTo(_current - 1) : null,
            onLeft: _hasPrevEvent == false
                ? null
                : () => _walkTimeline(current, forward: false),
            onRight: _hasNextEvent == false
                ? null
                : () => _walkTimeline(current, forward: true),
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
