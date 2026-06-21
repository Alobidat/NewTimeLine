/// Small shared chrome for the event surfaces (the modal sheet, the side panel via
/// [EventArticle], and the summary panel): section headers, meta pills, the severity
/// badge, and the entity-kind icon. Kept tiny so the two surfaces never drift apart.
///
/// The richer **media** building blocks live in their own files now (ADR-0024) — the
/// clips-first hero + gallery in `media_gallery.dart` and the fullscreen viewer in
/// `media_viewer.dart`. They are re-exported here so existing callers that imported
/// `MediaGallery` / `orderMediaClipsFirst` from `detail_widgets.dart` keep working.
library;

import 'package:flutter/material.dart';

import '../theme/severity.dart';

export 'media_gallery.dart'
    show MediaGallery, orderMediaClipsFirst, isShowableMedia;
export 'media_viewer.dart' show openMediaViewer, FullscreenViewer;

IconData entityIcon(String kind) => switch (kind) {
  'person' => Icons.person_outline,
  'place' => Icons.public,
  'org' => Icons.apartment,
  _ => Icons.label_outline,
};

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
