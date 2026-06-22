/// The per-page **gesture surface** of the vertical feed (ADR-0027). It is intentionally
/// transparent and carries no controls: the looping clip is painted ONCE behind the
/// [PageView] and the action rail + caption are pinned ONCE on top (both by [VideoFeed]), so
/// neither moves while the user pages between clips. This page owns ALL four swipe gestures:
///   • swipe **up**    → next clip,        • swipe **down** → previous clip,
///   • swipe **right** → the event graph,  • swipe **left** → next related event.
///
/// Vertical paging is driven here (not by the PageView's own physics) so a *gentle* swipe
/// advances: the default PageView snaps back unless the drag passes ~half the screen or is a
/// hard fling, which — because the pinned clip doesn't track the finger — feels like nothing
/// happens. We advance on a small distance OR a light flick instead.
library;

import 'package:flutter/material.dart';

class FeedItemView extends StatefulWidget {
  const FeedItemView({
    super.key,
    required this.onSwipeUpNext,
    required this.onSwipeDownPrev,
    required this.onSwipeRightGraph,
    required this.onSwipeLeftNext,
  });

  final VoidCallback onSwipeUpNext;
  final VoidCallback onSwipeDownPrev;
  final VoidCallback onSwipeRightGraph;
  final VoidCallback onSwipeLeftNext;

  @override
  State<FeedItemView> createState() => _FeedItemViewState();
}

class _FeedItemViewState extends State<FeedItemView> {
  // A swipe counts when EITHER the drag travels this far OR the flick is this fast.
  static const double _distance = 36; // px
  static const double _velocity = 110; // px/s
  static const double _hVelocity = 80; // px/s (lateral)

  double _dy = 0; // accumulated vertical drag for the current gesture

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      // ── Vertical: page the feed (next / previous). Driven manually for a low threshold.
      onVerticalDragStart: (_) => _dy = 0,
      onVerticalDragUpdate: (d) => _dy += d.primaryDelta ?? 0,
      onVerticalDragEnd: (d) {
        final v = d.primaryVelocity ?? 0;
        final dy = _dy;
        _dy = 0;
        if (v < -_velocity || dy < -_distance) {
          widget.onSwipeUpNext(); // up → next
        } else if (v > _velocity || dy > _distance) {
          widget.onSwipeDownPrev(); // down → previous
        }
      },
      // ── Horizontal: graph (right) / next related (left).
      onHorizontalDragEnd: (d) {
        final v = d.primaryVelocity ?? 0;
        if (v > _hVelocity) {
          widget.onSwipeRightGraph();
        } else if (v < -_hVelocity) {
          widget.onSwipeLeftNext();
        }
      },
      child: const SizedBox.expand(),
    );
  }
}
