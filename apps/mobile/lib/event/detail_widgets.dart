/// Reusable event-detail building blocks shared by the modal sheet and the inline
/// morphing panel via [EventArticle]: the clips-first expandable media gallery (hero +
/// swipe carousel + fullscreen viewer), the little pills/section headers, and the
/// severity badge. Kept in one place so the two surfaces never drift apart.
///
/// Media (ADR-0023): clips over images. A video clip is preferred as the hero; tapping
/// any tile opens a fullscreen swipeable viewer — pinch-zoom for images
/// (InteractiveViewer; photo_view is intentionally NOT a dependency), full controls for
/// video. Archival badges + captions are preserved.
library;

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/severity.dart';

IconData entityIcon(String kind) => switch (kind) {
  'person' => Icons.person_outline,
  'place' => Icons.public,
  'org' => Icons.apartment,
  _ => Icons.label_outline,
};

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

/// Clips-first media block: a large hero (prefers a video clip) plus a horizontal
/// thumbnail strip for the rest. Tapping any item opens the fullscreen viewer at that
/// index. Renders nothing when there is no showable media.
class MediaGallery extends StatelessWidget {
  const MediaGallery({super.key, required this.api, required this.items});

  final ApiClient api;
  final List<MediaRead> items;

  @override
  Widget build(BuildContext context) {
    final ordered = orderMediaClipsFirst(items);
    if (ordered.isEmpty) return const SizedBox.shrink();
    final hero = ordered.first;
    final rest = ordered.skip(1).toList();

    void open(int index) => _openViewer(context, api, ordered, index);

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          GestureDetector(
            onTap: () => open(0),
            child: _MediaFrame(
              media: hero,
              height: 220,
              child: _Thumb(api: api, media: hero, hero: true),
            ),
          ),
          if (rest.isNotEmpty) ...[
            const SizedBox(height: 8),
            SizedBox(
              height: 84,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: rest.length,
                separatorBuilder: (_, _) => const SizedBox(width: 8),
                itemBuilder: (_, i) => GestureDetector(
                  onTap: () => open(i + 1),
                  child: SizedBox(
                    width: 120,
                    child: _MediaFrame(
                      media: rest[i],
                      height: 84,
                      child: _Thumb(api: api, media: rest[i], hero: false),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

void _openViewer(
  BuildContext context,
  ApiClient api,
  List<MediaRead> items,
  int index,
) {
  Navigator.of(context).push(
    PageRouteBuilder<void>(
      opaque: false,
      barrierColor: Colors.black,
      pageBuilder: (_, _, _) =>
          _FullscreenViewer(api: api, items: items, initialIndex: index),
    ),
  );
}

/// Fixed-size rounded frame with optional caption + "archived" badge + a play glyph for
/// clips, used for every gallery tile regardless of kind.
class _MediaFrame extends StatelessWidget {
  const _MediaFrame({
    required this.media,
    required this.child,
    required this.height,
  });
  final MediaRead media;
  final Widget child;
  final double height;

  @override
  Widget build(BuildContext context) {
    final compact = height < 120;
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: Stack(
          fit: StackFit.expand,
          children: [
            child,
            if (media.kind == 'video')
              Center(
                child: Icon(
                  Icons.play_circle_fill,
                  size: compact ? 28 : 56,
                  color: Colors.white70,
                ),
              ),
            if (media.disposition == 'pin' && !compact)
              const Positioned(
                top: 6,
                left: 6,
                child: Chip(
                  label: Text('archived', style: TextStyle(fontSize: 11)),
                  avatar: Icon(Icons.lock, size: 14),
                  visualDensity: VisualDensity.compact,
                ),
              ),
            if (media.caption != null && !compact)
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  color: Colors.black54,
                  child: Text(
                    media.caption!,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Static poster for a tile: the image bytes, or (for a video) its thumbnail/poster
/// frame. Tiles never auto-play — playback happens in the fullscreen viewer.
class _Thumb extends StatelessWidget {
  const _Thumb({required this.api, required this.media, required this.hero});
  final ApiClient api;
  final MediaRead media;
  final bool hero;

  @override
  Widget build(BuildContext context) {
    // For images we show the bytes; for video we show the same raw URL (its thumbnail
    // is served behind the media id) under the play glyph drawn by _MediaFrame.
    return Image.network(
      api.mediaUrl(media.id),
      fit: BoxFit.cover,
      errorBuilder: (_, _, _) => ColoredBox(
        color: Colors.black26,
        child: Center(
          child: Icon(
            media.kind == 'video'
                ? Icons.movie_outlined
                : Icons.broken_image_outlined,
            size: hero ? 40 : 24,
          ),
        ),
      ),
      loadingBuilder: (ctx, child, p) =>
          p == null ? child : const Center(child: CircularProgressIndicator()),
    );
  }
}

/// Fullscreen, swipeable media viewer. Images pinch-zoom via [InteractiveViewer]; videos
/// play with full controls. Caption + archival badge shown beneath.
class _FullscreenViewer extends StatefulWidget {
  const _FullscreenViewer({
    required this.api,
    required this.items,
    required this.initialIndex,
  });
  final ApiClient api;
  final List<MediaRead> items;
  final int initialIndex;

  @override
  State<_FullscreenViewer> createState() => _FullscreenViewerState();
}

class _FullscreenViewerState extends State<_FullscreenViewer> {
  late final PageController _page =
      PageController(initialPage: widget.initialIndex);
  late int _current = widget.initialIndex;

  @override
  void dispose() {
    _page.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final m = widget.items[_current];
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        foregroundColor: Colors.white,
        title: Text('${_current + 1} / ${widget.items.length}'),
      ),
      extendBodyBehindAppBar: true,
      body: Stack(
        children: [
          PageView.builder(
            controller: _page,
            itemCount: widget.items.length,
            onPageChanged: (i) => setState(() => _current = i),
            itemBuilder: (_, i) {
              final item = widget.items[i];
              return item.kind == 'video'
                  ? _FullscreenVideo(
                      url: item.embedUrl ?? widget.api.mediaUrl(item.id),
                    )
                  : _ZoomableImage(url: widget.api.mediaUrl(item.id));
            },
          ),
          if (m.caption != null || m.disposition == 'pin')
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: Container(
                padding: const EdgeInsets.all(12),
                color: Colors.black54,
                child: Row(
                  children: [
                    if (m.disposition == 'pin') ...[
                      const Icon(Icons.lock, size: 16, color: Colors.white70),
                      const SizedBox(width: 6),
                    ],
                    Expanded(
                      child: Text(
                        m.caption ?? 'archived',
                        style: const TextStyle(color: Colors.white),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// A pinch/pan-zoomable network image (no photo_view dependency — plain Flutter).
class _ZoomableImage extends StatelessWidget {
  const _ZoomableImage({required this.url});
  final String url;

  @override
  Widget build(BuildContext context) {
    return InteractiveViewer(
      minScale: 1,
      maxScale: 5,
      child: Center(
        child: Image.network(
          url,
          fit: BoxFit.contain,
          errorBuilder: (_, _, _) => const Center(
            child: Icon(Icons.broken_image_outlined,
                size: 56, color: Colors.white54),
          ),
          loadingBuilder: (ctx, child, p) => p == null
              ? child
              : const Center(child: CircularProgressIndicator()),
        ),
      ),
    );
  }
}

/// Fullscreen video with a play/pause overlay and a scrub bar.
class _FullscreenVideo extends StatefulWidget {
  const _FullscreenVideo({required this.url});
  final String url;

  @override
  State<_FullscreenVideo> createState() => _FullscreenVideoState();
}

class _FullscreenVideoState extends State<_FullscreenVideo> {
  VideoPlayerController? _controller;
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
      await c.play();
      setState(() => _controller = c);
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
    if (_failed) {
      return const Center(
        child: Icon(Icons.error_outline, size: 56, color: Colors.white54),
      );
    }
    final c = _controller;
    if (c == null || !c.value.isInitialized) {
      return const Center(child: CircularProgressIndicator());
    }
    return GestureDetector(
      onTap: () =>
          setState(() => c.value.isPlaying ? c.pause() : c.play()),
      child: Stack(
        fit: StackFit.expand,
        children: [
          Center(
            child: AspectRatio(
              aspectRatio: c.value.aspectRatio,
              child: VideoPlayer(c),
            ),
          ),
          ValueListenableBuilder<VideoPlayerValue>(
            valueListenable: c,
            builder: (_, value, _) => value.isPlaying
                ? const SizedBox.shrink()
                : const Center(
                    child: Icon(Icons.play_arrow_rounded,
                        size: 72, color: Colors.white70),
                  ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: VideoProgressIndicator(
              c,
              allowScrubbing: true,
              padding: const EdgeInsets.all(12),
            ),
          ),
        ],
      ),
    );
  }
}

class Section extends StatelessWidget {
  const Section(this.title, {super.key});
  final String title;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 4),
    child: Text(
      title.toUpperCase(),
      style: Theme.of(context).textTheme.labelMedium?.copyWith(
        letterSpacing: 1.1,
        color: Colors.grey,
      ),
    ),
  );
}

class Pill extends StatelessWidget {
  const Pill(this.text, this.icon, {super.key});
  final String text;
  final IconData icon;
  @override
  Widget build(BuildContext context) => Chip(
    avatar: Icon(icon, size: 16),
    label: Text(text),
    visualDensity: VisualDensity.compact,
  );
}

class SeverityBadge extends StatelessWidget {
  const SeverityBadge(this.severity, {super.key});
  final int severity;
  @override
  Widget build(BuildContext context) => Chip(
    backgroundColor: severityColor(severity).withValues(alpha: 0.18),
    avatar: CircleAvatar(backgroundColor: severityColor(severity), radius: 8),
    label: Text('severity $severity'),
    visualDensity: VisualDensity.compact,
  );
}
