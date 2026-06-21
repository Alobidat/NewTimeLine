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
import 'feed_clip_player.dart';
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
    required this.onShare,
  });

  final VoidCallback onSwipeRightGraph;
  final VoidCallback onSwipeLeftNext;
  final VoidCallback onReact;
  final VoidCallback onComment;
  final VoidCallback onInfo;
  final void Function(bool up) onPromote;
  final VoidCallback onFollow;
  final VoidCallback onShare;
}

class FeedItemView extends StatelessWidget {
  const FeedItemView({
    super.key,
    required this.api,
    required this.item,
    required this.active,
    required this.preload,
    required this.callbacks,
  });

  final ApiClient api;
  final FeedItem item;

  /// This is the visible page (autoplay).
  final bool active;

  /// A neighbour we keep buffered for an instant swipe.
  final bool preload;
  final FeedItemCallbacks callbacks;

  /// How far a horizontal drag must travel (px) before it counts as a lateral swipe.
  static const double _swipeThreshold = 80;

  @override
  Widget build(BuildContext context) {
    final clipUrl =
        item.heroMediaId != null ? api.mediaUrl(item.heroMediaId!) : null;

    return GestureDetector(
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
      child: Container(
        color: Colors.black,
        child: Stack(
          fit: StackFit.expand,
          children: [
            FeedClipPlayer(
              url: clipUrl,
              active: active,
              preload: preload,
              // No posterUrl: the hero is a *video*, so its /raw URL isn't a decodable image —
              // passing it to Image.network just renders a broken image. The player shows a
              // neutral backdrop while the clip initialises instead.
              posterUrl: null,
            ),
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
              onReact: callbacks.onReact,
              onComment: callbacks.onComment,
              onInfo: callbacks.onInfo,
              onPromote: callbacks.onPromote,
              onFollow: callbacks.onFollow,
              onShare: callbacks.onShare,
              onOpenGraph: callbacks.onSwipeRightGraph,
            ),
          ],
        ),
      ),
    );
  }
}
