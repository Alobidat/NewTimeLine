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
///   • share   → live: opens a share sheet (Web Share API + Copy-link fallback) for a deep
///               link back onto this deployment (see `share.dart`). A read — never gated.
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
    required this.bookmarked,
    required this.onReact,
    required this.onComment,
    required this.onInfo,
    required this.onPromote,
    required this.onFollow,
    required this.onFollowCreator,
    required this.onBookmark,
    required this.onShare,
    required this.onOpenGraph,
    this.onAddVideo,
    this.hasPrevEvent,
    this.hasNextEvent,
  });

  final ApiClient api;
  final EventRead event;

  /// Whether the caller has this clip saved (filled vs outline bookmark icon).
  final bool bookmarked;
  final VoidCallback onReact;
  final VoidCallback onComment;
  final VoidCallback onInfo;

  /// up == true → promote, false → demote.
  final void Function(bool up) onPromote;
  final VoidCallback onFollow;

  /// Follow the clip's creator. Null when the event has no author (agent/seed events) —
  /// the button is hidden in that case.
  final VoidCallback? onFollowCreator;
  final VoidCallback onBookmark;
  final VoidCallback onShare;

  /// Opens the event's graph/timeline web — wired to the "Timeline web" button in the bottom bar.
  final VoidCallback onOpenGraph;

  /// Opens the "add a video" upload flow — wired to the bottom "Add video" button. Null hides
  /// the button (nested feeds without the home's upload entry point).
  final VoidCallback? onAddVideo;

  /// Whether the current event has an earlier / later related event — drives the bottom
  /// prev/next indicator (← previous / next →). Null while still being looked up (shown dim).
  final bool? hasPrevEvent;
  final bool? hasNextEvent;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // Right rail of round action buttons. Bounded between the top bar (top: 56 + safe
        // inset) and the caption (bottom: 96), then scaled with a bottom-anchored FittedBox so
        // the *whole* rail always fits the available height — every button stays visible and
        // correctly placed at any screen size, never truncated under the top-bar icons.
        Positioned(
          top: 56,
          right: 8,
          bottom: 96,
          child: SafeArea(
            bottom: false,
            child: FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.bottomCenter,
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
                  // Follow the creator — only for user-generated clips that carry an author.
                  if (onFollowCreator != null)
                    _RailButton(
                      key: const Key('rail-follow-creator'),
                      icon: Icons.video_camera_front_outlined,
                      label: 'Creator',
                      onTap: onFollowCreator!,
                    ),
                  _RailButton(
                    key: const Key('rail-bookmark'),
                    icon: bookmarked ? Icons.bookmark : Icons.bookmark_border,
                    label: 'Save',
                    onTap: onBookmark,
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
          ),
        ),
        // Bottom caption + swipe hints.
        Positioned(
          left: 12,
          right: 80,
          bottom: 24,
          child: _Caption(
            event: event,
            onOpenGraph: onOpenGraph,
            onAddVideo: onAddVideo,
            hasPrevEvent: hasPrevEvent,
            hasNextEvent: hasNextEvent,
          ),
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
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: InkResponse(
        onTap: onTap,
        radius: 26,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(7),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.35),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: Colors.white, size: 24),
            ),
            const SizedBox(height: 3),
            Text(
              label,
              style: const TextStyle(color: Colors.white, fontSize: 10),
            ),
          ],
        ),
      ),
    );
  }
}

class _Caption extends StatelessWidget {
  const _Caption({
    required this.event,
    required this.onOpenGraph,
    this.onAddVideo,
    this.hasPrevEvent,
    this.hasNextEvent,
  });
  final EventRead event;
  final VoidCallback onOpenGraph;
  final VoidCallback? onAddVideo;
  final bool? hasPrevEvent;
  final bool? hasNextEvent;

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
        // Indicator: whether this event has an earlier / later event in its timeline (a left /
        // right swipe lands there). Lit when available, dimmed when not, faded while loading.
        Row(
          children: [
            _RelIndicator(
              key: const Key('ind-prev-event'),
              icon: Icons.chevron_left,
              label: 'previous',
              state: hasPrevEvent,
            ),
            const SizedBox(width: 14),
            _RelIndicator(
              key: const Key('ind-next-event'),
              icon: Icons.chevron_right,
              label: 'next',
              state: hasNextEvent,
              iconTrailing: true,
            ),
          ],
        ),
        const SizedBox(height: 10),
        // Bottom action buttons: open the graph/timeline web, and add a video. (Both used to be
        // gestures — graph on swipe-right — now promoted to explicit buttons.)
        Row(
          children: [
            _BottomButton(
              key: const Key('feed-graph'),
              icon: Icons.account_tree_outlined,
              label: 'Timeline web',
              onTap: onOpenGraph,
            ),
            if (onAddVideo != null) ...[
              const SizedBox(width: 10),
              _BottomButton(
                key: const Key('feed-add-video'),
                icon: Icons.add,
                label: 'Add video',
                onTap: onAddVideo!,
              ),
            ],
          ],
        ),
      ],
    );
  }
}

/// A compact pill button for the feed's bottom bar (icon + label on a translucent dark chip).
class _BottomButton extends StatelessWidget {
  const _BottomButton({
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
    return Material(
      color: Colors.black.withValues(alpha: 0.45),
      shape: const StadiumBorder(),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, color: Colors.white, size: 18),
              const SizedBox(width: 6),
              Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A small prev/next-availability chip for the event's timeline. [state] == true → the related
/// event exists (lit), false → none in that direction (dimmed), null → still loading (faded).
class _RelIndicator extends StatelessWidget {
  const _RelIndicator({
    super.key,
    required this.icon,
    required this.label,
    required this.state,
    this.iconTrailing = false,
  });
  final IconData icon;
  final String label;
  final bool? state;
  final bool iconTrailing;

  @override
  Widget build(BuildContext context) {
    final available = state == true;
    final color = state == null
        ? Colors.white30
        : available
            ? Colors.white
            : Colors.white24;
    final icn = Icon(icon, color: color, size: 16);
    final txt = Text(
      label,
      style: TextStyle(
        color: color,
        fontSize: 11,
        fontWeight: available ? FontWeight.w600 : FontWeight.w400,
      ),
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: iconTrailing
          ? [txt, const SizedBox(width: 2), icn]
          : [icn, const SizedBox(width: 2), txt],
    );
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
          Text(
            'How do you feel about this?',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 12),
          ReactionBar(api: api, eventId: eventId),
        ],
      ),
    ),
  );
}
