/// The info / metadata + discussion sheet reached from a feed page's rail (ADR-0027 §5).
/// Rather than reimplement metadata + comments, it fetches the full [EventDetail] and hands
/// it to the shared [EventArticle] (ADR-0021) inside a draggable sheet — the exact same
/// layout the map/timeline experience uses (time, location, actors, sources, links,
/// reactions, threaded comments). Optionally scrolls straight to a section.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../event/event_article.dart';

/// Open the metadata/discussion sheet for [eventId]. [onSelectRelated] lets the host pivot
/// the feed to a related event instead of opening yet another sheet.
void showFeedInfoSheet(
  BuildContext context,
  ApiClient api,
  String eventId, {
  void Function(String eventId)? onSelectRelated,
}) {
  final future = api.event(eventId); // stable — the sheet rebuilds on every drag frame.
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => DraggableScrollableSheet(
      initialChildSize: 0.6,
      minChildSize: 0.35,
      maxChildSize: 0.95,
      expand: false,
      snap: true,
      snapSizes: const [0.6, 0.95],
      builder: (context, scrollController) => _Frame(
        child: FutureBuilder<EventDetail>(
          future: future,
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return Center(child: Text('Failed to load: ${snap.error}'));
            }
            return EventArticle(
              api: api,
              detail: snap.data!,
              scrollController: scrollController,
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
              onSelectRelated: onSelectRelated,
            );
          },
        ),
      ),
    ),
  );
}

/// Rounded surface + drag handle (mirrors the event sheet chrome so the two never drift).
class _Frame extends StatelessWidget {
  const _Frame({required this.child});
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
