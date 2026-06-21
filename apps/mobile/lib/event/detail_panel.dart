/// The inline, non-modal event detail — the right/left "morph" surface beside the map.
/// Fetches the full record + one-hop related events; tapping a related event asks the
/// parent to re-focus (which animates the camera and morphs this panel to the new event).
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import '../theme/severity.dart';
import 'detail_widgets.dart';

class DetailPanel extends StatefulWidget {
  const DetailPanel({
    super.key,
    required this.api,
    required this.detail,
    required this.onSelect,
    this.onClose,
  });

  final ApiClient api;

  /// The already-loaded event (the screen fetches it once to also drive the camera).
  final EventDetail detail;

  /// Re-focus on a related event (parent animates the map + morphs this panel).
  final void Function(String eventId) onSelect;
  final VoidCallback? onClose;

  @override
  State<DetailPanel> createState() => _DetailPanelState();
}

class _DetailPanelState extends State<DetailPanel> {
  late Future<List<RelatedEvent>> _related;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(DetailPanel old) {
    super.didUpdateWidget(old);
    if (old.detail.id != widget.detail.id) _load();
  }

  void _load() {
    _related = widget.api.related(widget.detail.id).catchError(
      (_) => <RelatedEvent>[],
    );
  }

  @override
  Widget build(BuildContext context) => _body(context, widget.detail);

  Widget _body(BuildContext context, EventDetail e) {
    final theme = Theme.of(context);
    final gallery = e.media
        .where((m) => m.kind == 'image' || m.kind == 'video')
        .toList();
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(e.title, style: theme.textTheme.titleLarge),
            ),
            if (widget.onClose != null)
              IconButton(
                tooltip: 'Back to overview',
                onPressed: widget.onClose,
                icon: const Icon(Icons.close),
              ),
          ],
        ),
        const SizedBox(height: 12),
        if (gallery.isNotEmpty) MediaGallery(api: widget.api, items: gallery),
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
        if (e.body != null && e.body!.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(e.body!, style: theme.textTheme.bodyMedium),
        ],
        const SizedBox(height: 20),
        _RelatedStrip(future: _related, onSelect: widget.onSelect),
        if (e.entities.isNotEmpty) ...[
          const SizedBox(height: 20),
          const Section('People, places & actors'),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: e.entities
                .map((er) => Chip(
                      avatar: Icon(entityIcon(er.entity.kind), size: 16),
                      label: Text('${er.entity.name} · ${er.role}'),
                      visualDensity: VisualDensity.compact,
                    ))
                .toList(),
          ),
        ],
        const SizedBox(height: 20),
        const Section('Sources'),
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
      ],
    );
  }
}

/// Horizontal strip of one-hop neighbours — the "navigate to a related event" affordance.
class _RelatedStrip extends StatelessWidget {
  const _RelatedStrip({required this.future, required this.onSelect});
  final Future<List<RelatedEvent>> future;
  final void Function(String eventId) onSelect;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<RelatedEvent>>(
      future: future,
      builder: (context, snap) {
        final items = snap.data ?? const <RelatedEvent>[];
        if (items.isEmpty) return const SizedBox.shrink();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Section('Connected events — tap to travel'),
            const SizedBox(height: 8),
            SizedBox(
              height: 96,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: items.length,
                separatorBuilder: (_, _) => const SizedBox(width: 8),
                itemBuilder: (_, i) =>
                    _RelatedCard(item: items[i], onTap: () => onSelect(items[i].event.id)),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _RelatedCard extends StatelessWidget {
  const _RelatedCard({required this.item, required this.onTap});
  final RelatedEvent item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = item.event;
    final arrow = item.direction == 'back'
        ? Icons.south_west
        : item.direction == 'forward'
            ? Icons.north_east
            : Icons.swap_horiz;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        width: 220,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: severityColor(e.severity).withValues(alpha: 0.6),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(arrow, size: 14, color: theme.colorScheme.primary),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(item.kind,
                      style: theme.textTheme.labelSmall,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Expanded(
              child: Text(e.title,
                  style: theme.textTheme.bodySmall,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ),
            Text(
              formatLabel(e.tStart, e.precision, instant: e.instant),
              style: theme.textTheme.labelSmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}
