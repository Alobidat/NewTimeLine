/// The inline, non-modal event detail — the right/left "morph" surface beside the map.
/// A thin wrapper over the shared [EventArticle] (ADR-0021): it keeps the panel-specific
/// affordances (a close button and in-place pivoting to a related event, which lets the
/// parent animate the camera and morph this panel) and delegates the whole layout to the
/// article so the panel and the modal sheet render identically.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import 'event_article.dart';

class DetailPanel extends StatelessWidget {
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
  Widget build(BuildContext context) {
    return EventArticle(
      api: api,
      detail: detail,
      onSelectRelated: onSelect,
      headerTrailing: onClose == null
          ? null
          : IconButton(
              tooltip: 'Back to overview',
              onPressed: onClose,
              icon: const Icon(Icons.close),
            ),
    );
  }
}
