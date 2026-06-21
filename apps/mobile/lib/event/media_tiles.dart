/// Tile primitives shared by the media gallery (ADR-0024): the rounded [MediaFrame] that
/// overlays a play glyph / archival badge / caption / "+N" affordance, the [MediaThumb]
/// poster that blur-ups via a [ShimmerBox] and never shows a broken tile, and the shimmer
/// placeholder itself. Kept apart from the gallery layout so each file stays small.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';

/// Rounded frame shared by hero + strip tiles: clips its child, overlays an optional play
/// glyph (clips), an "archived" badge (pinned media), a caption, and the gallery "+N more"
/// affordance on the overflow tile.
class MediaFrame extends StatelessWidget {
  const MediaFrame({
    super.key,
    required this.media,
    required this.child,
    required this.height,
    this.showPlayGlyph = true,
    this.overlayCount = 0,
  });

  final MediaRead media;
  final Widget child;
  final double height;

  /// Whether to draw the centred play glyph for a video tile.
  final bool showPlayGlyph;

  /// When > 0 this tile shows a "+N" scrim into the fullscreen carousel.
  final int overlayCount;

  @override
  Widget build(BuildContext context) {
    final compact = height < 120;
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: Stack(
          fit: StackFit.expand,
          children: [
            child,
            if (media.kind == 'video' && showPlayGlyph && overlayCount == 0)
              Center(
                child: Icon(
                  Icons.play_circle_fill,
                  size: compact ? 30 : 60,
                  color: Colors.white.withValues(alpha: 0.85),
                  shadows: const [Shadow(blurRadius: 8, color: Colors.black54)],
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
            if (overlayCount > 0)
              ColoredBox(
                color: Colors.black54,
                child: Center(
                  child: Text(
                    '+$overlayCount',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Static poster for a tile: the image bytes, or (for a video) its poster frame served
/// behind the media id. Shows a shimmer placeholder while decoding and a graceful glyph on
/// error — never a broken tile. Tiles never auto-play; the hero preview and the fullscreen
/// viewer own playback.
class MediaThumb extends StatelessWidget {
  const MediaThumb({
    super.key,
    required this.api,
    required this.media,
    required this.hero,
  });
  final ApiClient api;
  final MediaRead media;
  final bool hero;

  @override
  Widget build(BuildContext context) {
    return Image.network(
      api.mediaUrl(media.id),
      fit: BoxFit.cover,
      gaplessPlayback: true,
      errorBuilder: (_, _, _) => ColoredBox(
        color: Colors.black26,
        child: Center(
          child: Icon(
            media.kind == 'video'
                ? Icons.movie_outlined
                : Icons.broken_image_outlined,
            size: hero ? 40 : 24,
            color: Colors.white54,
          ),
        ),
      ),
      // Blur-up / shimmer while the bytes decode, then cross-fade the real image in.
      frameBuilder: (ctx, child, frame, wasSync) {
        if (wasSync) return child;
        return AnimatedSwitcher(
          duration: const Duration(milliseconds: 250),
          child: frame == null
              ? const ShimmerBox(key: ValueKey('shimmer'))
              : KeyedSubtree(key: const ValueKey('img'), child: child),
        );
      },
      loadingBuilder: (ctx, child, p) =>
          p == null ? child : const ShimmerBox(),
    );
  }
}

/// A tasteful animated shimmer used as a blur-up placeholder while media decodes.
class ShimmerBox extends StatefulWidget {
  const ShimmerBox({super.key});

  @override
  State<ShimmerBox> createState() => _ShimmerBoxState();
}

class _ShimmerBoxState extends State<ShimmerBox>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1200),
  )..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final base = Theme.of(context).colorScheme.surfaceContainerHighest;
    final hi = Theme.of(context).colorScheme.surfaceContainerHigh;
    return AnimatedBuilder(
      animation: _c,
      builder: (_, _) {
        final t = _c.value; // 0..1 sweep
        return DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment(-1 - t, 0),
              end: Alignment(1 - t, 0),
              colors: [base, hi, base],
              stops: const [0.35, 0.5, 0.65],
            ),
          ),
        );
      },
    );
  }
}
