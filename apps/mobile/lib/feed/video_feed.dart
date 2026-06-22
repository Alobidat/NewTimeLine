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
import 'feed_item.dart';
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
  });

  final ApiClient api;
  final AuthState auth;
  final FeedSource source;
  final FeedTab tab;

  @override
  State<VideoFeed> createState() => _VideoFeedState();
}

class _VideoFeedState extends State<VideoFeed>
    with AutomaticKeepAliveClientMixin {
  final PageController _page = PageController();
  final List<FeedItem> _items = [];

  /// Event ids the user has saved this session (drives the filled bookmark icon). Seeded
  /// optimistically on toggle — we don't pre-fetch each item's saved state to keep the feed
  /// request-light, so a previously-saved clip shows unfilled until the user taps it.
  final Set<String> _bookmarked = {};

  String? _cursor;
  bool _loading = false;
  bool _exhausted = false;
  Object? _error;
  int _current = 0;

  @override
  bool get wantKeepAlive => true; // keep each tab's scroll position + controllers.

  @override
  void initState() {
    super.initState();
    _loadMore();
  }

  @override
  void dispose() {
    _page.dispose();
    super.dispose();
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
          ),
        ),
      ),
    );
  }

  /// Swipe left: advance to the next forward-related event in the current timeline. Appends
  /// it to the feed (if not already present) and animates to it — a one-hop lateral walk.
  Future<void> _walkForward(FeedItem item) async {
    List<RelatedEvent> related;
    try {
      related =
          await widget.api.related(item.event.id, direction: 'forward');
    } catch (_) {
      related = const [];
    }
    if (!mounted) return;
    final next = related.isNotEmpty ? related.first.event : null;
    if (next == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No further event in this timeline.')),
      );
      return;
    }
    var idx = _items.indexWhere((i) => i.id == next.id);
    if (idx < 0) {
      setState(() => _items.add(FeedItem(event: next)));
      idx = _items.length - 1;
    }
    _page.animateToPage(
      idx,
      duration: const Duration(milliseconds: 350),
      curve: Curves.easeOutCubic,
    );
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

    // The active clip is rendered ONCE here, behind the PageView. On CanvasKit web a
    // video_player platform view placed *inside* a PageView is mis-positioned (pinned to the
    // viewport top as a strip), so we keep a single full-screen player outside the scrollable
    // and just switch its source as the page settles. The PageView carries the transparent
    // overlays (scrim + rail + gestures) on top.
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
            posterUrl: null,
          ),
        ),
        PageView.builder(
          controller: _page,
          scrollDirection: Axis.vertical,
          itemCount: _items.length,
          onPageChanged: (i) {
            setState(() => _current = i);
            // Warm the next two clips so the following swipes start instantly (FR-1.3).
            _prefetchUpcoming();
            // Page near the end → fetch the next page.
            if (i >= _items.length - 2) _loadMore();
          },
          itemBuilder: (context, i) {
            final item = _items[i];
            final active = i == _current;
            final preload = (i - _current).abs() == 1; // immediate neighbours only.
            return FeedItemView(
          key: ValueKey('feed-${widget.tab.slug}-${item.id}'),
          api: widget.api,
          item: item,
          active: active,
          preload: preload,
          bookmarked: _bookmarked.contains(item.id),
          callbacks: FeedItemCallbacks(
            onSwipeRightGraph: () => _openGraph(item),
            onSwipeLeftNext: () => _walkForward(item),
            onReact: () => _react(item),
            onComment: () => _comment(item),
            onInfo: () => _info(item),
            onPromote: (up) => _promote(item, up),
            onFollow: () => _follow(item),
            onFollowCreator:
                item.event.authorId != null ? () => _followCreator(item) : null,
            onBookmark: () => _bookmark(item),
            onShare: () => _share(item),
          ),
        );
          },
        ),
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
