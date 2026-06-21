/// The "many events → one view" surface: when a timeframe holds lots of events, this panel
/// shows the server-distilled [TimelineSummary] — a media montage, the headline
/// representatives, and the involved places/entities — instead of any single event. Tapping
/// a montage tile or a headline focuses that event (parent zooms the map + morphs to detail).
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import '../event/detail_widgets.dart';
import '../theme/severity.dart';

class SummaryPanel extends StatelessWidget {
  const SummaryPanel({
    super.key,
    required this.api,
    required this.summary,
    required this.loading,
    required this.onSelect,
    this.error,
  });

  final ApiClient api;
  final TimelineSummary? summary;
  final bool loading;
  final String? error;
  final void Function(String eventId) onSelect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final s = summary;
    if (error != null && s == null) {
      return Center(child: Text('Failed to load summary: $error'));
    }
    if (s == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final withMedia =
        s.representatives.where((r) => r.heroMediaId != null).toList();

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '${s.total} event${s.total == 1 ? '' : 's'}',
                style: theme.textTheme.titleLarge,
              ),
            ),
            if (loading)
              const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
          ],
        ),
        Text(
          '${formatYear(s.t0)} → ${formatYear(s.t1)}',
          style: theme.textTheme.bodyMedium
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        if (s.total == 0) ...[
          const SizedBox(height: 24),
          const Text('No events in this timeframe. Widen the timeline to explore.'),
        ],
        if (withMedia.isNotEmpty) ...[
          const SizedBox(height: 16),
          const Section('In pictures'),
          const SizedBox(height: 8),
          _Montage(api: api, reps: withMedia, onSelect: onSelect),
        ],
        if (s.topPlaces.isNotEmpty) ...[
          const SizedBox(height: 20),
          const Section('Where'),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: s.topPlaces
                .map((p) => Chip(
                      avatar: const Icon(Icons.place_outlined, size: 16),
                      label: Text('${p.label} · ${p.count}'),
                      visualDensity: VisualDensity.compact,
                    ))
                .toList(),
          ),
        ],
        if (s.topEntities.isNotEmpty) ...[
          const SizedBox(height: 20),
          const Section('Who & what'),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: s.topEntities
                .map((en) => Chip(
                      avatar: Icon(entityIcon(en.kind), size: 16),
                      label: Text(
                        en.eventCount != null
                            ? '${en.name} · ${en.eventCount}'
                            : en.name,
                      ),
                      visualDensity: VisualDensity.compact,
                    ))
                .toList(),
          ),
        ],
        if (s.representatives.isNotEmpty) ...[
          const SizedBox(height: 20),
          const Section('Headlines — tap to dive in'),
          const SizedBox(height: 4),
          ...s.representatives.map(
            (r) => _Headline(rep: r, onTap: () => onSelect(r.id)),
          ),
        ],
      ],
    );
  }
}

class _Montage extends StatelessWidget {
  const _Montage({required this.api, required this.reps, required this.onSelect});
  final ApiClient api;
  final List<SummaryRep> reps;
  final void Function(String eventId) onSelect;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 120,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: reps.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (_, i) {
          final r = reps[i];
          return GestureDetector(
            onTap: () => onSelect(r.id),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: SizedBox(
                width: 160,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Image.network(
                      api.mediaUrl(r.heroMediaId!),
                      fit: BoxFit.cover,
                      errorBuilder: (_, _, _) => ColoredBox(
                        color: severityColor(r.severity).withValues(alpha: 0.3),
                        child: const Center(
                          child: Icon(Icons.image_not_supported_outlined),
                        ),
                      ),
                      loadingBuilder: (ctx, child, p) =>
                          p == null ? child : const ColoredBox(color: Colors.black26),
                    ),
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: 0,
                      child: Container(
                        padding:
                            const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                        color: Colors.black54,
                        child: Text(
                          r.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: Colors.white, fontSize: 11),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _Headline extends StatelessWidget {
  const _Headline({required this.rep, required this.onTap});
  final SummaryRep rep;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: CircleAvatar(radius: 6, backgroundColor: severityColor(rep.severity)),
      title: Text(rep.title, maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        [
          formatLabel(rep.tStart, rep.precision),
          ?rep.geoLabel,
        ].join('  ·  '),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      onTap: onTap,
    );
  }
}
