/// The per-page **gesture surface** of the vertical feed (ADR-0027). It is intentionally
/// transparent and carries no controls: the looping clip is painted ONCE behind the
/// [PageView] and the action rail + caption are pinned ONCE on top (both by [VideoFeed]), so
/// neither moves while the user pages between clips. This page only claims the **horizontal
/// swipe** gestures so they don't fight the parent vertical [PageView]:
///   • swipe **right** → the event's graph/timeline web,
///   • swipe **left**  → the next related event in the current timeline.
library;

import 'package:flutter/material.dart';

/// A full-page transparent surface that turns a horizontal fling into a lateral navigation.
/// Vertical drags fall through to the parent [PageView]; taps/other gestures fall through to
/// the pinned overlay above and the clip below.
class FeedItemView extends StatelessWidget {
  const FeedItemView({
    super.key,
    required this.onSwipeRightGraph,
    required this.onSwipeLeftNext,
  });

  final VoidCallback onSwipeRightGraph;
  final VoidCallback onSwipeLeftNext;

  /// How far a horizontal drag must travel (px) before it counts as a lateral swipe.
  static const double _swipeThreshold = 80;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      // Claim horizontal drags only; vertical paging stays with the parent PageView.
      behavior: HitTestBehavior.opaque,
      onHorizontalDragEnd: (details) {
        final v = details.primaryVelocity ?? 0;
        if (v > _swipeThreshold) {
          onSwipeRightGraph(); // fling right → graph web
        } else if (v < -_swipeThreshold) {
          onSwipeLeftNext(); // fling left → next related event
        }
      },
      child: const SizedBox.expand(),
    );
  }
}
