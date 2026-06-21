/// Media-forward presentation (ADR-0024 / ADR-0023): the event's media block leads with
/// motion and pictures and treats prose as support.
///
///   * Hero — a **video clip** whenever one exists (muted, looping autoplay *preview*
///     where the platform allows it; tap → the fullscreen viewer with sound + controls).
///     Falls back to the best image, never to a broken tile.
///   * Gallery strip — the remaining media as larger thumbnails with a clear "+N" tile
///     that opens the fullscreen carousel at the first hidden item.
///   * Quality — a shimmer placeholder while images decode, aspect-ratio-respecting tiles,
///     and a graceful error glyph (never a broken tile). The hero height is capped on wide
///     screens so a single clip can't dominate the whole fold.
///
/// The fullscreen viewer is a swipeable carousel: images pinch/pan-zoom via
/// [InteractiveViewer] (photo_view is intentionally NOT a dependency), videos play with
/// sound and full controls.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../api/client.dart';
import '../api/models.dart';
import 'media_tiles.dart';
import 'media_viewer.dart';

export 'media_tiles.dart' show MediaFrame, MediaThumb, ShimmerBox;

/// Media a tile can actually render (image or video). Audio/embed are excluded from the
/// visual gallery — they degrade to nothing here rather than to a broken tile.
bool isShowableMedia(MediaRead m) => m.kind == 'image' || m.kind == 'video';

/// Order a media list clips-first: video before image, then by role (hero first) and the
/// item's natural order. Drives both the hero pick and the gallery sequence (ADR-0023).
List<MediaRead> orderMediaClipsFirst(List<MediaRead> items) {
  int kindRank(MediaRead m) => m.kind == 'video' ? 0 : 1;
  int roleRank(MediaRead m) => m.role == 'hero' ? 0 : 1;
  final sorted = [...items];
  sorted.sort((a, b) {
    final k = kindRank(a).compareTo(kindRank(b));
    if (k != 0) return k;
    return roleRank(a).compareTo(roleRank(b));
  });
  return sorted;
}

/// Media-first block shared by the modal sheet and the side panel: a prominent clip-first
/// hero plus a visible gallery strip with a "+N" affordance into the fullscreen carousel.
/// Renders nothing when there is no showable media.
class MediaGallery extends StatelessWidget {
  const MediaGallery({super.key, required this.api, required this.items});

  final ApiClient api;
  final List<MediaRead> items;

  /// Up to this many tiles sit in the strip; the rest collapse behind the "+N" tile.
  static const int _stripCap = 4;

  @override
  Widget build(BuildContext context) {
    final ordered = orderMediaClipsFirst(items.where(isShowableMedia).toList());
    if (ordered.isEmpty) return const SizedBox.shrink();
    final hero = ordered.first;
    final rest = ordered.skip(1).toList();

    void open(int index) => openMediaViewer(context, api, ordered, index);

    // Cap the hero height on wide screens so one clip can't eat the whole fold, but keep
    // it generous so media stays above the fold (ADR-0024).
    final w = MediaQuery.sizeOf(context).width;
    final heroHeight = w >= 720 ? 320.0 : (w * 0.62).clamp(200.0, 300.0);

    // When there are more tiles than fit, the strip shows (_stripCap - 1) individual
    // thumbnails plus one "+N" tile that stands in for the rest (itself included) and
    // opens the fullscreen carousel at the first item it represents.
    final hasOverflow = rest.length > _stripCap;
    final stripCount = hasOverflow ? _stripCap : rest.length;
    final overflow = hasOverflow ? rest.length - (stripCount - 1) : 0;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _HeroTile(api: api, media: hero, height: heroHeight, onTap: () => open(0)),
          if (rest.isNotEmpty) ...[
            const SizedBox(height: 8),
            SizedBox(
              height: 92,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: stripCount,
                separatorBuilder: (_, _) => const SizedBox(width: 8),
                itemBuilder: (_, i) {
                  // The last visible strip tile carries the "+N more" overlay.
                  final isOverflowTile = overflow > 0 && i == stripCount - 1;
                  final media = rest[i];
                  return GestureDetector(
                    onTap: () => open(i + 1),
                    child: SizedBox(
                      width: 128,
                      child: MediaFrame(
                        media: media,
                        height: 92,
                        overlayCount: isOverflowTile ? overflow : 0,
                        child: MediaThumb(api: api, media: media, hero: false),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// The hero. For a video clip it shows a muted, looping autoplay *preview* (no controls);
/// tap routes to the fullscreen viewer with sound. For an image it shows a large poster
/// with a shimmer placeholder. Degrades to a poster on any video failure.
class _HeroTile extends StatelessWidget {
  const _HeroTile({
    required this.api,
    required this.media,
    required this.height,
    required this.onTap,
  });

  final ApiClient api;
  final MediaRead media;
  final double height;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final Widget content = media.kind == 'video'
        ? _ClipPreview(
            url: media.embedUrl ?? api.mediaUrl(media.id),
            poster: MediaThumb(api: api, media: media, hero: true),
          )
        : MediaThumb(api: api, media: media, hero: true);

    return GestureDetector(
      onTap: onTap,
      child: MediaFrame(
        media: media,
        height: height,
        // The preview already signals "video"; only show the big play glyph for clips so
        // the user knows a tap brings sound + controls.
        showPlayGlyph: media.kind == 'video',
        child: content,
      ),
    );
  }
}

/// Muted, looping, controls-free clip preview for the hero. Shows the [poster] until the
/// first frame is ready, and falls back to the poster forever on any decode error so a
/// flaky clip never becomes a broken tile.
class _ClipPreview extends StatefulWidget {
  const _ClipPreview({required this.url, required this.poster});
  final String url;
  final Widget poster;

  @override
  State<_ClipPreview> createState() => _ClipPreviewState();
}

class _ClipPreviewState extends State<_ClipPreview> {
  VideoPlayerController? _controller;
  bool _ready = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final c = VideoPlayerController.networkUrl(Uri.parse(widget.url));
    try {
      await c.initialize();
      if (!mounted) {
        await c.dispose();
        return;
      }
      await c.setVolume(0); // muted preview
      await c.setLooping(true);
      // Autoplay where the platform allows it; a rejected play() must not throw past here.
      unawaited(c.play().catchError((_) {}));
      setState(() {
        _controller = c;
        _ready = true;
      });
    } catch (_) {
      await c.dispose();
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = _controller;
    if (_failed || !_ready || c == null || !c.value.isInitialized) {
      // Poster while initialising, and the permanent fallback on failure.
      return widget.poster;
    }
    return FittedBox(
      fit: BoxFit.cover,
      clipBehavior: Clip.hardEdge,
      child: SizedBox(
        width: c.value.size.width,
        height: c.value.size.height,
        child: VideoPlayer(c),
      ),
    );
  }
}

