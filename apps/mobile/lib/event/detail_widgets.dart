/// Reusable event-detail building blocks shared by the (legacy) modal sheet and the new
/// inline morphing panel: the media gallery (images + inline-playable video), the little
/// pills/section headers, and the severity badge. Kept in one place so the two surfaces
/// never drift apart.
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

/// Horizontal gallery of media tiles. Images render inline; videos show a poster that
/// initialises and plays the clip in place when tapped.
class MediaGallery extends StatelessWidget {
  const MediaGallery({
    super.key,
    required this.api,
    required this.items,
    this.height = 200,
  });
  final ApiClient api;
  final List<MediaRead> items;
  final double height;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: SizedBox(
        height: height,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: items.length,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (_, i) {
            final m = items[i];
            final tile = m.kind == 'video'
                ? _VideoTile(url: m.embedUrl ?? api.mediaUrl(m.id))
                : _ImageTile(url: api.mediaUrl(m.id));
            return _MediaFrame(media: m, child: tile);
          },
        ),
      ),
    );
  }
}

/// Fixed-size rounded frame with optional caption + "archived" badge, used for every
/// gallery item regardless of kind.
class _MediaFrame extends StatelessWidget {
  const _MediaFrame({required this.media, required this.child});
  final MediaRead media;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: SizedBox(
        width: 280,
        height: double.infinity,
        child: Stack(
          fit: StackFit.expand,
          children: [
            child,
            if (media.disposition == 'pin')
              const Positioned(
                top: 6,
                left: 6,
                child: Chip(
                  label: Text('archived', style: TextStyle(fontSize: 11)),
                  avatar: Icon(Icons.lock, size: 14),
                  visualDensity: VisualDensity.compact,
                ),
              ),
            if (media.caption != null)
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
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

class _ImageTile extends StatelessWidget {
  const _ImageTile({required this.url});
  final String url;

  @override
  Widget build(BuildContext context) => Image.network(
    url,
    fit: BoxFit.cover,
    errorBuilder: (_, _, _) => const ColoredBox(
      color: Colors.black26,
      child: Center(child: Icon(Icons.broken_image_outlined, size: 40)),
    ),
    loadingBuilder: (ctx, child, p) =>
        p == null ? child : const Center(child: CircularProgressIndicator()),
  );
}

/// A video that lazily initialises a [VideoPlayerController] on first tap, then plays
/// inline with a tap-to-pause overlay and a scrub bar.
class _VideoTile extends StatefulWidget {
  const _VideoTile({required this.url});
  final String url;

  @override
  State<_VideoTile> createState() => _VideoTileState();
}

class _VideoTileState extends State<_VideoTile> {
  VideoPlayerController? _controller;
  bool _initializing = false;
  bool _failed = false;

  Future<void> _start() async {
    setState(() => _initializing = true);
    final c = VideoPlayerController.networkUrl(Uri.parse(widget.url));
    try {
      await c.initialize();
      if (!mounted) {
        await c.dispose();
        return;
      }
      await c.play();
      setState(() {
        _controller = c;
        _initializing = false;
      });
    } catch (_) {
      await c.dispose();
      if (mounted) {
        setState(() {
          _initializing = false;
          _failed = true;
        });
      }
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
    if (c != null && c.value.isInitialized) {
      return GestureDetector(
        onTap: () =>
            setState(() => c.value.isPlaying ? c.pause() : c.play()),
        child: Stack(
          fit: StackFit.expand,
          children: [
            FittedBox(
              fit: BoxFit.cover,
              child: SizedBox(
                width: c.value.size.width,
                height: c.value.size.height,
                child: VideoPlayer(c),
              ),
            ),
            ValueListenableBuilder<VideoPlayerValue>(
              valueListenable: c,
              builder: (_, value, _) => value.isPlaying
                  ? const SizedBox.shrink()
                  : const Center(
                      child: Icon(Icons.play_arrow_rounded,
                          size: 56, color: Colors.white70),
                    ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: VideoProgressIndicator(c, allowScrubbing: true),
            ),
          ],
        ),
      );
    }
    return GestureDetector(
      onTap: _initializing || _failed ? null : _start,
      child: ColoredBox(
        color: Colors.black,
        child: Center(
          child: _initializing
              ? const CircularProgressIndicator()
              : Icon(
                  _failed ? Icons.error_outline : Icons.play_circle_outline,
                  size: 56,
                  color: Colors.white70,
                ),
        ),
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
