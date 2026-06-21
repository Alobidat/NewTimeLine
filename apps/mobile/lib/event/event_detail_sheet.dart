/// Expandable popup showing event detail: a media gallery (images + inline-playable
/// video), summary, entities, sources, the sub-timeline of deep-history subjects
/// (ADR-0005), and a button to *dig* the causal chain.
///
/// Presented as a [DraggableScrollableSheet] so it opens as a compact popup that the
/// user can drag up to (near) full screen and back down.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../dig/dig_screen.dart';
import '../domain/time_format.dart';
import '../search/results_list.dart';
import 'detail_widgets.dart';

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
        if (gallery.isNotEmpty) MediaGallery(api: api, items: gallery),
        Text(e.title, style: theme.textTheme.titleLarge),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Pill(formatLabel(e.tStart, e.precision, instant: e.instant), Icons.schedule),
            if (e.geoLabel != null) Pill(e.geoLabel!, Icons.place_outlined),
            if (e.category != null) Pill(e.category!, Icons.category_outlined),
            SeverityBadge(e.severity),
            Pill('${e.sourceCount} source(s)', Icons.link),
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
          Section('People, places & actors'),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: e.entities
                .map((er) => ActionChip(
                      avatar: Icon(entityIcon(er.entity.kind), size: 16),
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
        Section('Sources'),
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
          Section('Explore the history (sub-timeline)'),
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

// Shared detail widgets (media gallery, pills, sections, severity badge, entity icon)
// live in detail_widgets.dart so the inline panel and this sheet stay in sync.
