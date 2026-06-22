/// One full-screen page of the vertical feed (ADR-0027): the looping clip ([FeedClipPlayer])
/// with the TikTok [OverlayRail] on top, and the **horizontal swipe** gestures layered over
/// it — swipe **right** → the event's graph/timeline web, swipe **left** → the next related
/// event in the current timeline (a guided lateral walk).
///
/// Vertical swipes are NOT handled here — they belong to the parent vertical PageView
/// ([VideoFeed]); this page only claims horizontal drags so the two axes don't fight.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import 'feed_source.dart';
import 'overlay_rail.dart';

/// Callbacks the host ([VideoFeed]) supplies so a page can drive navigation/actions without
/// owning the feed list or the API plumbing.
class FeedItemCallbacks {
  const FeedItemCallbacks({
    required this.onSwipeRightGraph,
    required this.onSwipeLeftNext,
    required this.onReact,
    required this.onComment,
    required this.onInfo,
    required this.onPromote,
    required this.onFollow,
    required this.onFollowCreator,
    required this.onBookmark,
    required this.onShare,
  });

  final VoidCallback onSwipeRightGraph;
  final VoidCallback onSwipeLeftNext;
  final VoidCallback onReact;
  final VoidCallback onComment;
  final VoidCallback onInfo;
  final void Function(bool up) onPromote;
  final VoidCallback onFollow;

  /// Follow the clip's creator (only wired when the event has an author). Null → no creator.
  final VoidCallback? onFollowCreator;
  final VoidCallback onBookmark;
  final VoidCallback onShare;
}

class FeedItemView extends StatelessWidget {
  const FeedItemView({
    super.key,
    required this.api,
    required this.item,
    required this.active,
    required this.preload,
    required this.bookmarked,
    required this.callbacks,
  });

  final ApiClient api;
  final FeedItem item;

  /// This is the visible page (autoplay).
  final bool active;

  /// A neighbour we keep buffered for an instant swipe.
  final bool preload;

  /// Whether the caller has this clip saved (drives the filled bookmark icon).
  final bool bookmarked;
  final FeedItemCallbacks callbacks;

  /// How far a horizontal drag must travel (px) before it counts as a lateral swipe.
  static const double _swipeThreshold = 80;

  @override
  Widget build(BuildContext context) {
    // The clip itself is rendered ONCE behind the PageView by [VideoFeed] (a platform view
    // inside a PageView mis-positions on CanvasKit web), so a page is just the transparent
    // overlay layer — scrim + rail + the horizontal-swipe gestures — over that video.
    return GestureDetector(
      behavior: HitTestBehavior.opaque, // claim the whole page area for horizontal drags
      // Claim horizontal drags only; vertical paging stays with the parent PageView.
      onHorizontalDragEnd: (details) {
        final v = details.primaryVelocity ?? 0;
        if (v > _swipeThreshold) {
          // Drag/fling to the right → reveals the graph web.
          callbacks.onSwipeRightGraph();
        } else if (v < -_swipeThreshold) {
          // Drag/fling to the left → advance to the next related event.
          callbacks.onSwipeLeftNext();
        }
      },
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Subtle bottom scrim so the caption stays legible over bright clips.
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
          OverlayRail(
            api: api,
            event: item.event,
            bookmarked: bookmarked,
            onReact: callbacks.onReact,
            onComment: callbacks.onComment,
            onInfo: callbacks.onInfo,
            onPromote: callbacks.onPromote,
            onFollow: callbacks.onFollow,
            onFollowCreator: callbacks.onFollowCreator,
            onBookmark: callbacks.onBookmark,
            onShare: callbacks.onShare,
            onOpenGraph: callbacks.onSwipeRightGraph,
          ),
        ],
      ),
    );
  }
}
