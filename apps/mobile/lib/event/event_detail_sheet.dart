/// Expandable popup showing event detail: a media gallery (images + inline-playable
/// video), summary, entities, sources, the sub-timeline of deep-history subjects
/// (ADR-0005), and a button to *dig* the causal chain.
///
/// Presented as a [DraggableScrollableSheet] so it opens as a compact popup that the
/// user can drag up to (near) full screen and back down.
library;

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../dig/dig_screen.dart';
import '../domain/time_format.dart';
import '../search/results_list.dart';
import '../theme/severity.dart';

/// Open the detail popup for [eventId]; fetches the full record via [api].
void showEventDetail(BuildContext context, ApiClient api, String eventId) {
  // Fetch once, up front — the sheet's builder runs on every drag frame, so the
  // future must be stable or we'd re-hit the API while the user drags.
  final future = api.event(eventId);
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => DraggableScrollableSheet(
      initialChildSize: 0.5,
      minChildSize: 0.3,
      maxChildSize: 0.95,
      expand: false,
      snap: true,
      snapSizes: const [0.5, 0.95],
      builder: (context, scrollController) => _SheetFrame(
        child: FutureBuilder<EventDetail>(
          future: future,
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return Center(child: Text('Failed to load: ${snap.error}'));
            }
            return _DetailBody(api, snap.data!, scrollController);
          },
        ),
      ),
    ),
  );
}

/// Rounded surface + drag handle wrapper shared by every state of the sheet.
class _SheetFrame extends StatelessWidget {
  const _SheetFrame({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surface,
      clipBehavior: Clip.antiAlias,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 10, bottom: 6),
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: scheme.onSurfaceVariant.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _DetailBody extends StatelessWidget {
  const _DetailBody(this.api, this.e, this.scrollController);
  final ApiClient api;
  final EventDetail e;
  final ScrollController scrollController;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Anything we can show inline: images plus videos (kind video, or an embed
    // that points straight at a media file).
    final gallery = e.media
        .where((m) => m.kind == 'image' || m.kind == 'video')
        .toList();
    return ListView(
      controller: scrollController,
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        if (gallery.isNotEmpty) _MediaGallery(api: api, items: gallery),
        Text(e.title, style: theme.textTheme.titleLarge),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            _Pill(formatLabel(e.tStart, e.precision, instant: e.instant), Icons.schedule),
            if (e.geoLabel != null) _Pill(e.geoLabel!, Icons.place_outlined),
            if (e.category != null) _Pill(e.category!, Icons.category_outlined),
            _SeverityBadge(e.severity),
            _Pill('${e.sourceCount} source(s)', Icons.link),
          ],
        ),
        if (e.summary != null) ...[
          const SizedBox(height: 16),
          Text(e.summary!, style: theme.textTheme.bodyMedium),
        ],
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => DigScreen(api: api, root: e)),
          ),
          icon: const Icon(Icons.account_tree_outlined),
          label: const Text('Dig the history — what led here & what it caused'),
        ),
        if (e.entities.isNotEmpty) ...[
          const SizedBox(height: 20),
          _Section('People, places & actors'),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: e.entities
                .map((er) => ActionChip(
                      avatar: Icon(_entityIcon(er.entity.kind), size: 16),
                      label: Text('${er.entity.name} · ${er.role}'),
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => ResultsScreen(
                            api: api,
                            title: er.entity.name,
                            future: api.eventsByEntities([er.entity.id]),
                          ),
                        ),
                      ),
                    ))
                .toList(),
          ),
        ],
        const SizedBox(height: 20),
        _Section('Sources'),
        if (e.sources.isEmpty)
          const Text('No sources attached.')
        else
          ...e.sources.map(
            (s) => ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.article_outlined),
              title: Text(s.title ?? s.domain),
              subtitle: Text('${s.publisher ?? s.domain} · ${s.url}',
                  maxLines: 1, overflow: TextOverflow.ellipsis),
            ),
          ),
        if (e.references.isNotEmpty) ...[
          const SizedBox(height: 12),
          _Section('Explore the history (sub-timeline)'),
          ...e.references.map(
            (r) => ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.history_edu_outlined),
              title: Text(r.label),
              subtitle: Text('${formatLabel(r.tStart, r.precision)}'
                  '${r.detail != null ? ' — ${r.detail}' : ''}'),
            ),
          ),
        ],
      ],
    );
  }
}

IconData _entityIcon(String kind) => switch (kind) {
  'person' => Icons.person_outline,
  'place' => Icons.public,
  'org' => Icons.apartment,
  _ => Icons.label_outline,
};

/// Horizontal gallery of media tiles. Images render inline; videos show a poster
/// that initialises and plays the clip in place when tapped.
class _MediaGallery extends StatelessWidget {
  const _MediaGallery({required this.api, required this.items});
  final ApiClient api;
  final List<MediaRead> items;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: SizedBox(
        height: 200,
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

/// Fixed-size rounded frame with optional caption + "archived" badge, used for
/// every gallery item regardless of kind.
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
        height: 200,
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
        loadingBuilder: (ctx, child, p) => p == null
            ? child
            : const Center(child: CircularProgressIndicator()),
      );
}

/// A video that lazily initialises a [VideoPlayerController] on first tap, then
/// plays inline with a tap-to-pause overlay and a scrub bar.
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
        onTap: () => setState(
          () => c.value.isPlaying ? c.pause() : c.play(),
        ),
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
            // Play glyph while paused.
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
    // Poster: black with a play button (or spinner / error glyph).
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

class _Section extends StatelessWidget {
  const _Section(this.title);
  final String title;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 4),
    child: Text(
      title.toUpperCase(),
      style: Theme.of(context).textTheme.labelMedium?.copyWith(
            letterSpacing: 1.1, color: Colors.grey,
          ),
    ),
  );
}

class _Pill extends StatelessWidget {
  const _Pill(this.text, this.icon);
  final String text;
  final IconData icon;
  @override
  Widget build(BuildContext context) => Chip(
    avatar: Icon(icon, size: 16),
    label: Text(text),
    visualDensity: VisualDensity.compact,
  );
}

class _SeverityBadge extends StatelessWidget {
  const _SeverityBadge(this.severity);
  final int severity;
  @override
  Widget build(BuildContext context) => Chip(
    backgroundColor: severityColor(severity).withValues(alpha: 0.18),
    avatar: CircleAvatar(backgroundColor: severityColor(severity), radius: 8),
    label: Text('severity $severity'),
    visualDensity: VisualDensity.compact,
  );
}
