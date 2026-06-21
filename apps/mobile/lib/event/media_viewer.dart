/// The fullscreen, swipeable media viewer reached by tapping any gallery tile (ADR-0023).
/// Images pinch/pan-zoom via [InteractiveViewer] (photo_view is intentionally NOT a
/// dependency); videos play with **sound** and full controls (play/pause + scrub bar).
/// Caption + archival badge are shown beneath. Opened via [openMediaViewer].
library;

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../api/client.dart';
import '../api/models.dart';

/// Push the fullscreen carousel over the current route, starting at [index].
void openMediaViewer(
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
          FullscreenViewer(api: api, items: items, initialIndex: index),
    ),
  );
}

/// Swipeable fullscreen carousel over a media list.
class FullscreenViewer extends StatefulWidget {
  const FullscreenViewer({
    super.key,
    required this.api,
    required this.items,
    required this.initialIndex,
  });
  final ApiClient api;
  final List<MediaRead> items;
  final int initialIndex;

  @override
  State<FullscreenViewer> createState() => _FullscreenViewerState();
}

class _FullscreenViewerState extends State<FullscreenViewer> {
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
                  ? FullscreenVideo(
                      // Active page autoplays with sound; others stay paused so only one
                      // clip plays at a time.
                      url: item.embedUrl ?? widget.api.mediaUrl(item.id),
                      active: i == _current,
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

/// Fullscreen video with sound, a play/pause overlay and a scrub bar. Plays only while
/// [active] (the visible carousel page); pauses when swiped away.
class FullscreenVideo extends StatefulWidget {
  const FullscreenVideo({super.key, required this.url, this.active = true});
  final String url;
  final bool active;

  @override
  State<FullscreenVideo> createState() => _FullscreenVideoState();
}

class _FullscreenVideoState extends State<FullscreenVideo> {
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
      if (widget.active) await c.play();
      setState(() => _controller = c);
    } catch (_) {
      await c.dispose();
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  void didUpdateWidget(FullscreenVideo old) {
    super.didUpdateWidget(old);
    final c = _controller;
    if (c == null) return;
    if (widget.active && !old.active) {
      c.play();
    } else if (!widget.active && old.active) {
      c.pause();
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
      onTap: () => setState(() => c.value.isPlaying ? c.pause() : c.play()),
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
