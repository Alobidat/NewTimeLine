/// The TikTok-style overlay over a feed page (ADR-0027, social-and-feed §5): a vertical
/// **right rail** led by the poster's avatar, then a single smart **React** button, comment,
/// save, and share — plus a **bottom caption** strip (title + meta + description with a "…more"
/// that opens the article).
///
/// Rail (top → bottom):
///   • author avatar → tap opens the creator's profile; a "+" badge follows them when the
///     caller doesn't already (user-generated clips only).
///   • React → tap toggles **Love** (the `like` reaction; heart turns red). Long-press opens a
///     mutually-exclusive Love / Promote / Demote selector; the active one shows colored.
///   • comment → opens the threaded discussion page.
///   • save → bookmark toggle.
///   • share → tap opens the share sheet; long-press **reposts** the clip to the caller's
///     followers.
/// The old separate promote/demote, follow-event, follow-creator and info buttons are gone —
/// follow moved onto the avatar, info moved to the caption "…more".
library;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import '../profile/avatar.dart';

/// The caller's current (mutually-exclusive) stance on a clip, derived by the host from the
/// `like` reaction + the promote vote. Drives the React button's icon + color.
enum ReactState { none, loved, promoted, demoted }

/// A choice from the React long-press selector.
enum ReactChoice { love, promote, demote }

/// The overlay placed on top of each [FeedClipPlayer]. Stateless beyond the callbacks it
/// fires; the heavy interaction widgets are opened as sheets/pages by the host.
class OverlayRail extends StatelessWidget {
  const OverlayRail({
    super.key,
    required this.api,
    required this.event,
    required this.bookmarked,
    required this.reactState,
    required this.followsAuthor,
    required this.onReactLove,
    required this.onReactMenu,
    required this.onComment,
    required this.onBookmark,
    required this.onShare,
    required this.onRepost,
    required this.onInfo,
    required this.onOpenGraph,
    this.author,
    this.authorKind = 'user',
    this.onOpenCreator,
    this.onFollowAuthor,
    this.onAddVideo,
    this.stats,
  });

  final ApiClient api;
  final EventRead event;

  /// Who the clip is attributed to (the uploading user, or an entity like NASA for agent
  /// clips) — identity for the avatar + follow badge.
  final CommentAuthor? author;

  /// 'user' (open profile on tap) or 'entity' (no personal profile). Drives the caption label.
  final String authorKind;

  /// Aggregate engagement counts for [event], shown under the matching buttons. Null while the
  /// counts are still loading (buttons show no number until then).
  final EventStats? stats;

  /// Whether the caller has this clip saved (filled vs outline bookmark icon).
  final bool bookmarked;

  /// The caller's mutually-exclusive stance (love/promote/demote/none) — colors the React icon.
  final ReactState reactState;

  /// Whether the caller already follows the clip's author (hides the "+" follow badge).
  final bool followsAuthor;

  /// React: single tap toggles Love; long-press lifts a Love/Promote/Demote menu up from the
  /// button (the [Offset] is the press position so the menu anchors there).
  final VoidCallback onReactLove;
  final void Function(Offset at) onReactMenu;
  final VoidCallback onComment;
  final VoidCallback onBookmark;

  /// Share: tap opens the share sheet; long-press lifts a menu up from the button (Repost / share
  /// link) anchored at the press position.
  final VoidCallback onShare;
  final void Function(Offset at) onRepost;

  /// Opens the event's article/metadata sheet — wired to the caption's "…more".
  final VoidCallback onInfo;

  /// Open the clip creator's profile (avatar tap). Null when the event has no author.
  final VoidCallback? onOpenCreator;

  /// Follow the clip's creator (the "+" badge). Null when the event has no author.
  final VoidCallback? onFollowAuthor;

  /// Opens the event's graph/timeline web — wired to the "Timeline web" button in the bottom bar.
  final VoidCallback onOpenGraph;

  /// Opens the "add a video" upload flow — wired to the bottom "Add video" button. Null hides
  /// the button (nested feeds without the home's upload entry point).
  final VoidCallback? onAddVideo;

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
                  // Author avatar + follow — the uploading user, or the clip's primary entity
                  // (e.g. NASA) for agent-curated world events. Always present when attributable.
                  if (author != null)
                    _AvatarRailButton(
                      author: author,
                      followsAuthor: followsAuthor,
                      onOpenCreator: onOpenCreator,
                      onFollowAuthor: onFollowAuthor,
                    ),
                  _RailButton(
                    key: const Key('rail-react'),
                    icon: _reactIcon,
                    iconColor: _reactColor,
                    label: _reactLabel,
                    count: stats?.reactions,
                    onTap: onReactLove,
                    onLongPress: onReactMenu,
                  ),
                  _RailButton(
                    key: const Key('rail-comment'),
                    icon: Icons.mode_comment_outlined,
                    label: 'Comment',
                    count: stats?.comments,
                    onTap: onComment,
                  ),
                  _RailButton(
                    key: const Key('rail-bookmark'),
                    icon: bookmarked ? Icons.bookmark : Icons.bookmark_border,
                    iconColor: bookmarked ? Colors.amberAccent : Colors.white,
                    label: 'Save',
                    count: stats?.bookmarks,
                    onTap: onBookmark,
                  ),
                  _RailButton(
                    key: const Key('rail-share'),
                    icon: Icons.reply_outlined, // mirrored arrow reads as share/repost
                    label: 'Share',
                    onTap: onShare,
                    onLongPress: onRepost,
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
            author: author,
            authorKind: authorKind,
            onOpenCreator: onOpenCreator,
            onInfo: onInfo,
            onOpenGraph: onOpenGraph,
            onAddVideo: onAddVideo,
          ),
        ),
      ],
    );
  }

  IconData get _reactIcon => switch (reactState) {
        ReactState.loved => Icons.favorite,
        ReactState.promoted => Icons.arrow_upward,
        ReactState.demoted => Icons.arrow_downward,
        ReactState.none => Icons.favorite_border,
      };

  Color get _reactColor => switch (reactState) {
        ReactState.loved => Colors.redAccent,
        ReactState.promoted => Colors.lightGreenAccent,
        ReactState.demoted => Colors.orangeAccent,
        ReactState.none => Colors.white,
      };

  String get _reactLabel => switch (reactState) {
        ReactState.loved => 'Loved',
        ReactState.promoted => 'Promoted',
        ReactState.demoted => 'Demoted',
        ReactState.none => 'Love',
      };
}

/// The poster's avatar at the top of the rail: tap opens their profile, and a "+" badge follows
/// them when the caller doesn't already. Falls back to initials (never a generic person icon).
class _AvatarRailButton extends StatelessWidget {
  const _AvatarRailButton({
    required this.author,
    required this.followsAuthor,
    required this.onOpenCreator,
    required this.onFollowAuthor,
  });

  final CommentAuthor? author;
  final bool followsAuthor;
  final VoidCallback? onOpenCreator;
  final VoidCallback? onFollowAuthor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: SizedBox(
        width: 52,
        height: 56,
        child: Stack(
          clipBehavior: Clip.none,
          alignment: Alignment.topCenter,
          children: [
            InkResponse(
              key: const Key('rail-author'),
              onTap: onOpenCreator,
              radius: 28,
              child: Container(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 1.5),
                ),
                child: Avatar(
                  label: author?.label ?? '',
                  url: author?.avatarUrl,
                  radius: 22,
                ),
              ),
            ),
            // "+" follow badge, bottom-centre over the avatar — only when not already following.
            if (!followsAuthor && onFollowAuthor != null)
              Positioned(
                bottom: -2,
                child: InkResponse(
                  key: const Key('rail-follow-badge'),
                  onTap: onFollowAuthor,
                  radius: 16,
                  child: Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      color: Colors.redAccent,
                      shape: BoxShape.circle,
                      border: Border.all(color: Colors.white, width: 1.5),
                    ),
                    child: const Icon(Icons.add, color: Colors.white, size: 14),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _RailButton extends StatelessWidget {
  const _RailButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
    this.onLongPress,
    this.iconColor = Colors.white,
    this.count,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  /// Long-press handler; receives the global press position so the host can lift a popup menu
  /// up from the button itself (not a bottom drawer).
  final void Function(Offset globalPosition)? onLongPress;
  final Color iconColor;

  /// Engagement count shown under the icon (TikTok-style). Null → show the action [label]
  /// instead (e.g. Share, or while counts load).
  final int? count;

  /// 1234 → "1.2k", 1_200_000 → "1.2m"; small numbers unchanged.
  static String _fmt(int n) {
    if (n >= 1000000) return '${(n / 1000000).toStringAsFixed(n % 1000000 == 0 ? 0 : 1)}m';
    if (n >= 1000) return '${(n / 1000).toStringAsFixed(n % 1000 == 0 ? 0 : 1)}k';
    return '$n';
  }

  @override
  Widget build(BuildContext context) {
    final showBadge = count != null && count! > 0;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onLongPressStart:
            onLongPress == null ? null : (d) => onLongPress!(d.globalPosition),
        child: InkResponse(
          onTap: onTap,
          radius: 26,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
            // Icon circle + a top-right count badge (notification-style, info-coloured).
            Stack(
              clipBehavior: Clip.none,
              children: [
                Container(
                  padding: const EdgeInsets.all(7),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.35),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(icon, color: iconColor, size: 24),
                ),
                if (showBadge)
                  Positioned(
                    bottom: -4,
                    right: -6,
                    child: _CountBadge(text: _fmt(count!)),
                  ),
              ],
            ),
            const SizedBox(height: 3),
            Text(
              label,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 10,
                shadows: [Shadow(blurRadius: 4, color: Colors.black87)],
              ),
            ),
          ],
          ),
        ),
      ),
    );
  }
}

/// A small notification-style count badge with an "info" look (translucent blue pill, white
/// text), sat at the top-right corner of a rail icon.
class _CountBadge extends StatelessWidget {
  const _CountBadge({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 16),
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: const Color(0xFF2F88FF), // info blue
        borderRadius: BorderRadius.circular(9),
        border: Border.all(color: Colors.white, width: 1),
      ),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 9,
          fontWeight: FontWeight.w700,
          height: 1.2,
        ),
      ),
    );
  }
}

class _Caption extends StatelessWidget {
  const _Caption({
    required this.event,
    required this.onInfo,
    required this.onOpenGraph,
    this.author,
    this.authorKind = 'user',
    this.onOpenCreator,
    this.onAddVideo,
  });
  final EventRead event;
  final CommentAuthor? author;
  final String authorKind;
  final VoidCallback? onOpenCreator;
  final VoidCallback onInfo;
  final VoidCallback onOpenGraph;
  final VoidCallback? onAddVideo;

  @override
  Widget build(BuildContext context) {
    final meta = [
      formatLabel(event.tStart, event.precision, instant: event.instant),
      if (event.geoLabel != null) event.geoLabel!,
      if (event.category != null) event.category!,
    ].join('  ·  ');
    final summary = event.summary?.trim() ?? '';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Author attribution (user-generated clips only) — who posted this, tappable to their
        // profile; the avatar + follow live on the rail.
        if (author != null) ...[
          GestureDetector(
            key: const Key('caption-author'),
            onTap: onOpenCreator,
            child: Text(
              authorKind == 'entity' ? author!.label : '@${author!.handle}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.w700,
                shadows: [Shadow(blurRadius: 6, color: Colors.black87)],
              ),
            ),
          ),
          const SizedBox(height: 4),
        ],
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
        // Description with a trailing "…more" that opens the full article (info moved here from
        // the rail). The whole line is tappable so the small "more" target is forgiving.
        if (summary.isNotEmpty) ...[
          const SizedBox(height: 6),
          GestureDetector(
            key: const Key('caption-more'),
            onTap: onInfo,
            child: Text.rich(
              TextSpan(
                children: [
                  TextSpan(text: '${_clip(summary)} '),
                  TextSpan(
                    text: 'more',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
                    recognizer: TapGestureRecognizer()..onTap = onInfo,
                  ),
                ],
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Colors.white70,
                fontSize: 13,
                shadows: [Shadow(blurRadius: 6, color: Colors.black87)],
              ),
            ),
          ),
        ],
        const SizedBox(height: 10),
        // Bottom action buttons: open the graph/timeline web, and add a video.
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

  /// Trim a long summary to a caption-friendly length so the trailing "more" always shows.
  static String _clip(String s) {
    const max = 120;
    if (s.length <= max) return s;
    return '${s.substring(0, max).trimRight()}…';
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

/// The React long-press selector: a compact sheet to pick a single mutually-exclusive stance
/// (Love / Promote / Demote). Returns the chosen [ReactChoice], or null if dismissed. The
/// [current] stance is highlighted so re-picking it (the host) toggles it back off.
Future<ReactChoice?> showReactSelector(
  BuildContext context,
  ReactState current,
  Offset at,
) {
  return _showHorizontalPicker<ReactChoice>(context, at, [
    _PickerOption(ReactChoice.love, 'react-choice-love', Icons.favorite, 'Love',
        Colors.redAccent, current == ReactState.loved),
    _PickerOption(ReactChoice.promote, 'react-choice-promote', Icons.arrow_upward,
        'Promote', Colors.lightGreenAccent, current == ReactState.promoted),
    _PickerOption(ReactChoice.demote, 'react-choice-demote', Icons.arrow_downward,
        'Demote', Colors.orangeAccent, current == ReactState.demoted),
  ]);
}

/// What the Share long-press picker can do.
enum ShareChoice { repost, shareLink }

/// The Share long-press picker (icons expanding left from the button): repost, or share a link.
Future<ShareChoice?> showShareSelector(
  BuildContext context,
  Offset at, {
  required bool reposted,
}) {
  return _showHorizontalPicker<ShareChoice>(context, at, [
    _PickerOption(ShareChoice.repost, 'share-choice-repost', Icons.repeat,
        reposted ? 'Reposted' : 'Repost', Colors.lightGreenAccent, reposted),
    _PickerOption(ShareChoice.shareLink, 'share-choice-link', Icons.ios_share,
        'Link', Colors.lightBlueAccent, false),
  ]);
}

/// One option in a horizontal long-press picker.
class _PickerOption<T> {
  const _PickerOption(this.value, this.keyName, this.icon, this.label, this.color, this.active);
  final T value;
  final String keyName;
  final IconData icon;
  final String label;
  final Color color;
  final bool active;
}

/// Show the [options] as the SAME rail-style icons expanding **horizontally to the left** of the
/// pressed button (at global [at]); tapping one returns it, tapping elsewhere dismisses. A
/// transparent route so it overlays the feed and animates the icons sliding out from the button.
Future<T?> _showHorizontalPicker<T>(
  BuildContext context,
  Offset at,
  List<_PickerOption<T>> options,
) {
  return Navigator.of(context).push<T>(
    PageRouteBuilder<T>(
      opaque: false,
      barrierColor: Colors.black.withValues(alpha: 0.2),
      barrierDismissible: true,
      barrierLabel: 'Dismiss',
      transitionDuration: const Duration(milliseconds: 170),
      reverseTransitionDuration: const Duration(milliseconds: 120),
      pageBuilder: (ctx, anim, _) {
        final size = MediaQuery.of(ctx).size;
        return Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => Navigator.of(ctx).pop(),
              ),
            ),
            Positioned(
              // Vertically centre the row on the press point; anchor its RIGHT edge just left
              // of the button so the icons grow leftward.
              top: (at.dy - 34).clamp(0.0, size.height - 72),
              right: (size.width - at.dx + 6).clamp(0.0, size.width - 60),
              child: FadeTransition(
                opacity: anim,
                child: SlideTransition(
                  position: Tween<Offset>(
                    begin: const Offset(0.35, 0),
                    end: Offset.zero,
                  ).animate(CurvedAnimation(parent: anim, curve: Curves.easeOutCubic)),
                  child: _PickerRow<T>(
                    options: options,
                    onPick: (v) => Navigator.of(ctx).pop(v),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    ),
  );
}

/// The horizontal strip of rail-style icon buttons shown by [_showHorizontalPicker].
class _PickerRow<T> extends StatelessWidget {
  const _PickerRow({required this.options, required this.onPick});
  final List<_PickerOption<T>> options;
  final ValueChanged<T> onPick;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.6),
          borderRadius: BorderRadius.circular(36),
          border: Border.all(color: Colors.white24),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final o in options)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: InkResponse(
                  key: Key(o.keyName),
                  onTap: () => onPick(o.value),
                  radius: 28,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: o.active
                              ? o.color.withValues(alpha: 0.25)
                              : Colors.white.withValues(alpha: 0.12),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(o.icon,
                            color: o.active ? o.color : Colors.white, size: 24),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        o.label,
                        style: TextStyle(
                          color: o.active ? o.color : Colors.white,
                          fontSize: 10,
                          fontWeight: o.active ? FontWeight.w700 : FontWeight.w400,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
