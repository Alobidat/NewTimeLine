/// The full-screen, looping clip player for one feed page (ADR-0027). Distinct from the
/// event media viewer's [FullscreenVideo] (which plays *with sound + scrub controls*): the
/// feed wants the TikTok behaviour — **muted, looping autoplay** while the page is the
/// active one, paused (and rewound) when off-screen, tap to toggle mute/play.
///
/// To keep memory bounded the controller is created lazily and disposed as soon as the page
/// leaves the small "near the viewport" window (the parent [VideoFeed] only marks 2-3 pages
/// active/preload at a time). When there is no clip url the player shows a static poster so
/// the feed never renders a blank or broken page.
library;

import 'dart:math' as math;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import 'web_video.dart';

/// A muted, looping clip filling its box, with cover-fit (BoxFit.cover semantics) so it
/// behaves like a TikTok video. [active] drives autoplay; [preload] keeps the controller
/// initialized (buffered) without playing, so a swipe to it starts instantly.
class FeedClipPlayer extends StatefulWidget {
  const FeedClipPlayer({
    super.key,
    required this.url,
    required this.active,
    this.preload = false,
    this.posterUrl,
    this.onSwipe,
  });

  /// The clip url, or null when the event has no playable hero clip (poster-only).
  final String? url;

  /// Whether this is the visible page (autoplays + loops).
  final bool active;

  /// Keep the controller buffered though not the active page (a neighbour).
  final bool preload;

  /// Optional still image shown behind/instead of the clip (e.g. a thumbnail).
  final String? posterUrl;

  /// Web only: a swipe detected directly on the `<video>` element (the clip is the topmost DOM
  /// element on the web, so it — not Flutter's gesture layer — receives swipes over it). Off the
  /// web this is unused: the feed's Flutter [GestureDetector] handles paging. See [webVideoView].
  final WebSwipe? onSwipe;

  @override
  State<FeedClipPlayer> createState() => _FeedClipPlayerState();
}

class _FeedClipPlayerState extends State<FeedClipPlayer> {
  VideoPlayerController? _controller;
  bool _failed = false;
  bool _muted = true;

  // On the web the clip is rendered by a raw HTML <video> (see build) — never the
  // video_player controller, whose platform view can't be cover-fit.
  bool get _wanted =>
      !kIsWeb && widget.url != null && (widget.active || widget.preload);

  @override
  void initState() {
    super.initState();
    if (_wanted) _init();
  }

  @override
  void didUpdateWidget(FeedClipPlayer old) {
    super.didUpdateWidget(old);
    if (old.url != widget.url) {
      _disposeController();
      _failed = false;
      if (_wanted) _init();
      return;
    }
    if (_wanted && _controller == null && !_failed) {
      _init();
      return;
    }
    if (!_wanted && _controller != null) {
      _disposeController();
      setState(() {});
      return;
    }
    _syncPlayback();
  }

  Future<void> _init() async {
    final c = VideoPlayerController.networkUrl(Uri.parse(widget.url!));
    try {
      await c.initialize();
      if (!mounted) {
        await c.dispose();
        return;
      }
      await c.setLooping(true);
      await c.setVolume(_muted ? 0 : 1);
      _controller = c;
      _syncPlayback();
      setState(() {});
    } catch (_) {
      await c.dispose();
      if (mounted) setState(() => _failed = true);
    }
  }

  /// Play only while the active page; pause + rewind when it scrolls away.
  void _syncPlayback() {
    final c = _controller;
    if (c == null || !c.value.isInitialized) return;
    if (widget.active) {
      c.play();
    } else {
      c.pause();
      c.seekTo(Duration.zero);
    }
  }

  void _disposeController() {
    _controller?.dispose();
    _controller = null;
  }

  void _onTap() {
    final c = _controller;
    if (c == null || !widget.active) return;
    setState(() {
      _muted = !_muted;
      c.setVolume(_muted ? 0 : 1);
      if (!c.value.isPlaying) c.play();
    });
  }

  @override
  void dispose() {
    _disposeController();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Web: a full-bleed HTML <video> (object-fit: cover), muted-autoplay-loop. No controller,
    // no FittedBox — the element styles itself. Critically, NO Flutter-painted background here:
    // a ColoredBox/Container composites *above* the platform view in CanvasKit and would hide
    // the clip. The bare platform view lets the clip show with the overlays (rail/scrim) on top.
    if (kIsWeb) {
      final url = widget.url;
      return url == null
          ? const ColoredBox(color: Colors.black)
          : webVideoView(url, muted: true, onSwipe: widget.onSwipe);
    }
    return GestureDetector(
      onTap: _onTap,
      behavior: HitTestBehavior.opaque,
      child: Stack(
        fit: StackFit.expand,
        children: [
          _surface(),
          if (widget.active && _muted && _controller != null)
            const Positioned(
              right: 12,
              top: 12,
              child: Icon(Icons.volume_off, color: Colors.white70, size: 22),
            ),
        ],
      ),
    );
  }

  Widget _surface() {
    final c = _controller;
    if (c != null && c.value.isInitialized) {
      // Cover-fit, TikTok-style: scale the clip to fill the page and crop the overflow.
      // We size the video box *explicitly* to the cover dimensions (rather than relying on
      // FittedBox) because on the web the player is an HTML <video> platform view that
      // FittedBox can't transform — a landscape clip would otherwise letterbox into a strip.
      final vs = c.value.size;
      return ClipRect(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final boxW = constraints.maxWidth, boxH = constraints.maxHeight;
            final vw = vs.width <= 0 ? boxW : vs.width;
            final vh = vs.height <= 0 ? boxH : vs.height;
            final scale = math.max(boxW / vw, boxH / vh); // cover
            final w = vw * scale, h = vh * scale;
            return OverflowBox(
              minWidth: w, maxWidth: w, minHeight: h, maxHeight: h,
              child: SizedBox(width: w, height: h, child: VideoPlayer(c)),
            );
          },
        ),
      );
    }
    // No clip / still loading / failed: poster or a neutral backdrop.
    return _poster();
  }

  Widget _poster() {
    final poster = widget.posterUrl;
    return Container(
      color: Colors.black,
      alignment: Alignment.center,
      child: poster != null
          ? Image.network(
              poster,
              fit: BoxFit.cover,
              width: double.infinity,
              height: double.infinity,
              errorBuilder: (_, _, _) => _glyph(),
              loadingBuilder: (ctx, child, p) =>
                  p == null ? child : _glyph(),
            )
          : _glyph(),
    );
  }

  Widget _glyph() => Center(
    child: Icon(
      _failed ? Icons.error_outline : Icons.movie_creation_outlined,
      color: Colors.white24,
      size: 64,
    ),
  );
}
