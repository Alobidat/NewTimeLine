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

import 'dart:ui' show ImageFilter;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import 'web_video.dart';

/// A muted, looping clip shown at its TRUE aspect ratio (BoxFit.contain — never cropped), over
/// a blurred, dimmed cover of itself so the letterbox area reads as a soft backdrop rather than
/// dead black. "Best mode": every edge of the media is always visible, scaled to fit the page.
/// [active] drives autoplay; [preload] keeps the controller initialized (buffered) without
/// playing, so a swipe to it starts instantly.
class FeedClipPlayer extends StatefulWidget {
  const FeedClipPlayer({
    super.key,
    required this.url,
    required this.active,
    this.isClip = true,
    this.preload = false,
    this.posterUrl,
  });

  /// The hero media url, or null when the event has no hero (placeholder).
  final String? url;

  /// Whether [url] is a playable clip (video/embed). When false the hero is a still image and is
  /// rendered full-bleed as a photo — a `<video>` can't decode a JPEG, which showed a black
  /// screen. Image heroes are Flutter-painted (no `<video>` platform view), so on the web the
  /// feed's [GestureDetector] handles swipes over them normally.
  final bool isClip;

  /// Whether this is the visible page (autoplays + loops).
  final bool active;

  /// Keep the controller buffered though not the active page (a neighbour).
  final bool preload;

  /// Optional still image shown behind/instead of the clip (e.g. a thumbnail).
  final String? posterUrl;

  @override
  State<FeedClipPlayer> createState() => _FeedClipPlayerState();
}

class _FeedClipPlayerState extends State<FeedClipPlayer> {
  VideoPlayerController? _controller;
  bool _failed = false;
  bool _muted = true;

  // On the web the clip is rendered by a raw HTML <video> (see build) — never the
  // video_player controller, whose platform view can't be cover-fit. Image heroes never use a
  // controller (they're drawn as a photo), so a non-clip hero is never "wanted".
  bool get _wanted =>
      !kIsWeb &&
      widget.isClip &&
      widget.url != null &&
      (widget.active || widget.preload);

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
    final url = widget.url;

    // Image hero (most historical events have a photo, not a clip): render it full-bleed. This
    // is Flutter-painted on both platforms — on the web there's no <video> platform view, so the
    // feed's GestureDetector receives swipes over it normally. Feeding such a url to a <video>
    // is what produced the "new label, black screen, not playing" cards.
    if (url != null && !widget.isClip) {
      return _coverImage(url);
    }

    // Web: a full-bleed HTML <video> (object-fit: contain — never cropped), muted-autoplay-loop.
    // No controller, no FittedBox — the element styles itself. Critically, NO Flutter-painted
    // background here: a ColoredBox/Container composites *above* the platform view in CanvasKit
    // and would hide the clip. The bare platform view lets the clip show with overlays on top.
    if (kIsWeb) {
      return url == null
          ? const ColoredBox(color: Colors.black)
          : webVideoView(url, muted: true, posterUrl: widget.posterUrl);
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
      // Contain-fit ("best mode"): show the whole clip at its true aspect ratio, never cropping
      // an edge, over a blurred + dimmed cover of itself so the bars beside a portrait/landscape
      // clip read as a soft backdrop (matching the image hero in [_coverImage]). Both layers are
      // Textures from the same controller — a single decode is rendered twice, no extra cost.
      // (This path is native-only; the web clip is a self-styling <video>, see build.)
      final vs = c.value.size;
      final vw = vs.width <= 0 ? 1.0 : vs.width;
      final vh = vs.height <= 0 ? 1.0 : vs.height;
      return ColoredBox(
        color: Colors.black,
        child: Stack(
          fit: StackFit.expand,
          children: [
            ImageFiltered(
              imageFilter: ImageFilter.blur(sigmaX: 28, sigmaY: 28),
              child: FittedBox(
                fit: BoxFit.cover,
                clipBehavior: Clip.hardEdge,
                child: SizedBox(width: vw, height: vh, child: VideoPlayer(c)),
              ),
            ),
            const ColoredBox(color: Colors.black38),
            // The real clip, full aspect ratio, centred — scaled to fit with every edge visible.
            Center(
              child: AspectRatio(
                aspectRatio: vw / vh,
                child: VideoPlayer(c),
              ),
            ),
          ],
        ),
      );
    }
    // No clip / still loading / failed: poster or a neutral backdrop.
    return _poster();
  }

  /// A photo hero shown at its TRUE aspect ratio (BoxFit.contain — never cropped or stretched),
  /// over a blurred, darkened cover of the same image so the letterbox area isn't dead black.
  /// Falls back to the neutral glyph if the image can't load, so a card is never blank.
  Widget _coverImage(String url) {
    final sharp = Image.network(
      url,
      fit: BoxFit.contain, // respect the image's aspect ratio
      errorBuilder: (_, _, _) => _glyph(),
      loadingBuilder: (ctx, child, p) => p == null ? child : _glyph(),
    );
    return ColoredBox(
      color: Colors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Blurred + dimmed fill so the bars beside a portrait/landscape photo read as a soft
          // backdrop rather than black voids (Instagram-style).
          ImageFiltered(
            imageFilter: ImageFilter.blur(sigmaX: 28, sigmaY: 28),
            child: Image.network(
              url,
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => const ColoredBox(color: Colors.black),
            ),
          ),
          const ColoredBox(color: Colors.black38),
          // The real photo, full aspect ratio, centred.
          Center(child: sharp),
        ],
      ),
    );
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
