/// Modal-sheet host for the standard event article (ADR-0021). A thin wrapper: it owns
/// the [DraggableScrollableSheet] chrome and the "Dig the history" button, then delegates
/// the whole body to the shared [EventArticle] so the sheet and the side panel render the
/// identical layout.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../dig/dig_screen.dart';
import '../search/results_list.dart';
import 'event_article.dart';

/// Open the detail popup for [eventId]; fetches the full record via [api].
void showEventDetail(BuildContext context, ApiClient api, String eventId) =>
    showEventDetailById(context, api, eventId);

/// Open the detail sheet for [eventId]. Named distinctly so the article can re-open a
/// related event in a fresh sheet when no in-place pivot is supplied.
void showEventDetailById(BuildContext context, ApiClient api, String eventId) {
  // Fetch once, up front — the sheet's builder runs on every drag frame, so the future
  // must be stable or we'd re-hit the API while the user drags.
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
            return _SheetBody(api, snap.data!, scrollController);
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

/// The sheet's body: the shared article, plus the sheet-only "Dig the history" button.
/// Entity chips pivot to a results screen; related events open in a fresh sheet (the
/// article's default when no in-place pivot is supplied).
class _SheetBody extends StatelessWidget {
  const _SheetBody(this.api, this.e, this.scrollController);
  final ApiClient api;
  final EventDetail e;
  final ScrollController scrollController;

  @override
  Widget build(BuildContext context) {
    return EventArticle(
      api: api,
      detail: e,
      scrollController: scrollController,
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      footerExtra: FilledButton.icon(
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => DigScreen(api: api, root: e)),
        ),
        icon: const Icon(Icons.account_tree_outlined),
        label: const Text('Dig the history — what led here & what it caused'),
      ),
      onSelectEntity: (entity) => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => ResultsScreen(
            api: api,
            title: entity.name,
            future: api.eventsByEntities([entity.id]),
          ),
        ),
      ),
    );
  }
}
