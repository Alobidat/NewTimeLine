/// Bottom sheet showing full event detail: summary, sources, and the sub-timeline
/// of deep-history subjects the event references (ADR-0005).
library;

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../domain/time_format.dart';
import '../theme/severity.dart';
import '../timeline/timeline_controller.dart';

/// Open the detail sheet for [eventId], loading the full record lazily.
void showEventDetail(
  BuildContext context,
  TimelineController controller,
  String eventId,
) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => FractionallySizedBox(
      heightFactor: 0.8,
      child: FutureBuilder<EventDetail>(
        future: controller.fetchDetail(eventId),
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('Failed to load: ${snap.error}'));
          }
          return _DetailBody(snap.data!);
        },
      ),
    ),
  );
}

class _DetailBody extends StatelessWidget {
  const _DetailBody(this.e);
  final EventDetail e;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        Text(e.title, style: theme.textTheme.titleLarge),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            _Pill(
              formatLabel(e.tStart, e.precision, instant: e.instant),
              Icons.schedule,
            ),
            if (e.geoLabel != null) _Pill(e.geoLabel!, Icons.place_outlined),
            if (e.category != null) _Pill(e.category!, Icons.category_outlined),
            _SeverityBadge(e.severity),
            _Pill('confidence ${e.confidence}', Icons.verified_outlined),
            _Pill('${e.sourceCount} source(s)', Icons.link),
          ],
        ),
        if (e.summary != null) ...[
          const SizedBox(height: 16),
          Text(e.summary!, style: theme.textTheme.bodyMedium),
        ],
        if (e.body != null) ...[
          const SizedBox(height: 12),
          Text(e.body!, style: theme.textTheme.bodyMedium),
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
              subtitle: Text(
                '${s.publisher ?? s.domain} · ${s.url}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        const SizedBox(height: 12),
        _Section('Explore the history (sub-timeline)'),
        if (e.references.isEmpty)
          Text(
            'No deeper history linked yet.',
            style: theme.textTheme.bodySmall,
          )
        else
          ...e.references.map(
            (r) => ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.history_edu_outlined),
              title: Text(r.label),
              subtitle: Text(
                '${formatLabel(r.tStart, r.precision)}'
                '${r.detail != null ? ' — ${r.detail}' : ''}',
              ),
            ),
          ),
      ],
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
      style: Theme.of(
        context,
      ).textTheme.labelMedium?.copyWith(letterSpacing: 1.1, color: Colors.grey),
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
