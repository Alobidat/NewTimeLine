/// The TikTok-style overlay over a feed page (ADR-0027, social-and-feed §5): a vertical
/// **right rail** of action buttons (react, comment, promote/vote, follow author, share,
/// info) plus a **bottom caption** strip (title + meta + a swipe-hint).
///
/// Wiring status (Phase 4-F shell):
///   • react   → live: opens a compact reaction sheet backed by [ApiClient.toggleReaction]
///               (reuses the existing [ReactionBar]).
///   • comment → live: opens the existing threaded [CommentsSection] in a bottom sheet.
///   • info    → live: opens the metadata sheet (reuses [EventArticle] sections).
///   • promote → live for events via the reaction substrate (up = like, down = dislike,
///               ADR-0025) until the dedicated promote endpoint lands (social-and-feed §2).
///   • follow  → STUB: no follow endpoint yet (Phase 4-B). Calls a thin client method and
///               tolerates failure with a snackbar. TODO: wire to POST /follows.
///   • share   → STUB: copies/► a share intent is platform work (IU2). Shows a snackbar.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import '../event/reaction_bar.dart';

/// The overlay placed on top of each [FeedClipPlayer]. Stateless beyond the callbacks it
/// fires; the heavy interaction widgets are opened as sheets by the host.
class OverlayRail extends StatelessWidget {
  const OverlayRail({
    super.key,
    required this.api,
    required this.event,
    required this.onReact,
    required this.onComment,
    required this.onInfo,
    required this.onPromote,
    required this.onFollow,
    required this.onShare,
    required this.onOpenGraph,
  });

  final ApiClient api;
  final EventRead event;
  final VoidCallback onReact;
  final VoidCallback onComment;
  final VoidCallback onInfo;

  /// up == true → promote, false → demote.
  final void Function(bool up) onPromote;
  final VoidCallback onFollow;
  final VoidCallback onShare;
  final VoidCallback onOpenGraph;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // Right rail of round action buttons.
        Positioned(
          right: 8,
          bottom: 120,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _RailButton(
                key: const Key('rail-promote-up'),
                icon: Icons.arrow_upward,
                label: 'Promote',
                onTap: () => onPromote(true),
              ),
              _RailButton(
                key: const Key('rail-promote-down'),
                icon: Icons.arrow_downward,
                label: 'Demote',
                onTap: () => onPromote(false),
              ),
              _RailButton(
                key: const Key('rail-react'),
                icon: Icons.favorite_border,
                label: 'React',
                onTap: onReact,
              ),
              _RailButton(
                key: const Key('rail-comment'),
                icon: Icons.mode_comment_outlined,
                label: 'Comment',
                onTap: onComment,
              ),
              _RailButton(
                key: const Key('rail-follow'),
                icon: Icons.person_add_alt_1_outlined,
                label: 'Follow',
                onTap: onFollow,
              ),
              _RailButton(
                key: const Key('rail-share'),
                icon: Icons.share_outlined,
                label: 'Share',
                onTap: onShare,
              ),
              _RailButton(
                key: const Key('rail-info'),
                icon: Icons.info_outline,
                label: 'Info',
                onTap: onInfo,
              ),
            ],
          ),
        ),
        // Bottom caption + swipe hints.
        Positioned(
          left: 12,
          right: 80,
          bottom: 24,
          child: _Caption(event: event, onOpenGraph: onOpenGraph),
        ),
      ],
    );
  }
}

class _RailButton extends StatelessWidget {
  const _RailButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: InkResponse(
        onTap: onTap,
        radius: 28,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.35),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: Colors.white, size: 26),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: const TextStyle(color: Colors.white, fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }
}

class _Caption extends StatelessWidget {
  const _Caption({required this.event, required this.onOpenGraph});
  final EventRead event;
  final VoidCallback onOpenGraph;

  @override
  Widget build(BuildContext context) {
    final meta = [
      formatLabel(event.tStart, event.precision, instant: event.instant),
      if (event.geoLabel != null) event.geoLabel!,
      if (event.category != null) event.category!,
    ].join('  ·  ');

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          event.title,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 17,
            fontWeight: FontWeight.w600,
            shadows: [Shadow(blurRadius: 6, color: Colors.black87)],
          ),
        ),
        const SizedBox(height: 6),
        Text(
          meta,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: Colors.white70,
            fontSize: 13,
            shadows: [Shadow(blurRadius: 6, color: Colors.black87)],
          ),
        ),
        const SizedBox(height: 8),
        // Affordances hinting the lateral gestures (also tappable for discoverability).
        Row(
          children: [
            _Hint(
              key: const Key('hint-graph'),
              icon: Icons.account_tree_outlined,
              text: 'Swipe → web',
              onTap: onOpenGraph,
            ),
            const SizedBox(width: 12),
            const _Hint(
              icon: Icons.east,
              text: 'Swipe ← next in timeline',
            ),
          ],
        ),
      ],
    );
  }
}

class _Hint extends StatelessWidget {
  const _Hint({super.key, required this.icon, required this.text, this.onTap});
  final IconData icon;
  final String text;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final row = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: Colors.white60, size: 14),
        const SizedBox(width: 4),
        Text(text, style: const TextStyle(color: Colors.white60, fontSize: 11)),
      ],
    );
    return onTap == null ? row : GestureDetector(onTap: onTap, child: row);
  }
}

/// A compact reaction sheet (reuses the live [ReactionBar]) shown when the rail's React
/// button is tapped — keeps the immersive feed but gives the full like/dislike/important/
/// doubt toggles backed by the existing interaction API.
Future<void> showReactionSheet(
  BuildContext context,
  ApiClient api,
  String eventId,
) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: Theme.of(context).colorScheme.surface,
    builder: (_) => Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('How do you feel about this?',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          ReactionBar(api: api, eventId: eventId),
        ],
      ),
    ),
  );
}
