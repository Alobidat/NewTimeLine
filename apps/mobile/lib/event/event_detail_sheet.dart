/// Bottom sheet showing full event detail: media, summary, entities, sources, the
/// sub-timeline of deep-history subjects (ADR-0005), and a button to *dig* the causal chain.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../dig/dig_screen.dart';
import '../domain/time_format.dart';
import '../search/results_list.dart';
import '../theme/severity.dart';

/// Open the detail sheet for [eventId]; fetches the full record via [api].
void showEventDetail(BuildContext context, ApiClient api, String eventId) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => FractionallySizedBox(
      heightFactor: 0.85,
      child: FutureBuilder<EventDetail>(
        future: api.event(eventId),
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('Failed to load: ${snap.error}'));
          }
          return _DetailBody(api, snap.data!);
        },
      ),
    ),
  );
}

class _DetailBody extends StatelessWidget {
  const _DetailBody(this.api, this.e);
  final ApiClient api;
  final EventDetail e;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final images = e.media.where((m) => m.kind == 'image').toList();
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        if (images.isNotEmpty) _MediaStrip(api: api, images: images),
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
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => DigScreen(api: api, root: e)),
          ),
          icon: const Icon(Icons.account_tree_outlined),
          label: const Text('Dig the history — what led here & what it caused'),
        ),
        if (e.summary != null) ...[
          const SizedBox(height: 16),
          Text(e.summary!, style: theme.textTheme.bodyMedium),
        ],
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

class _MediaStrip extends StatelessWidget {
  const _MediaStrip({required this.api, required this.images});
  final ApiClient api;
  final List<MediaRead> images;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: SizedBox(
        height: 180,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: images.length,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (_, i) {
            final m = images[i];
            return ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: Stack(
                children: [
                  Image.network(
                    api.mediaUrl(m.id),
                    width: 260, height: 180, fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => Container(
                      width: 260, height: 180, color: Colors.black26,
                      alignment: Alignment.center,
                      child: const Icon(Icons.broken_image_outlined, size: 40),
                    ),
                    loadingBuilder: (ctx, child, p) =>
                        p == null ? child : const SizedBox(
                          width: 260, height: 180,
                          child: Center(child: CircularProgressIndicator()),
                        ),
                  ),
                  if (m.disposition == 'pin')
                    const Positioned(
                      top: 6, left: 6,
                      child: Chip(
                        label: Text('archived', style: TextStyle(fontSize: 11)),
                        avatar: Icon(Icons.lock, size: 14),
                        visualDensity: VisualDensity.compact,
                      ),
                    ),
                ],
              ),
            );
          },
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
