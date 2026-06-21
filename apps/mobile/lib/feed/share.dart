/// Sharing a feed clip (social-and-feed §5, FR-1.4 / FR-3.1). Turns the rail's "Share" tap
/// into a real action: a bottom sheet that offers the OS share sheet (Web Share API on the
/// web) and a reliable **Copy link** fallback. The link is a deep link onto the current
/// deployment (`<origin>/?event=<id>`, see [AppConfig.shareBaseUrl]); the app opens that
/// event on launch (see `main.dart`), so a shared link lands the recipient on the clip.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/models.dart';
import '../config.dart';
// Web Share API on the web; a no-op (returns false) elsewhere.
import 'share_stub.dart' if (dart.library.js_interop) 'share_web.dart';

/// The shareable deep link for [eventId]. Falls back to the bare id when no public base URL
/// is configured (native without `SHARE_BASE_URL`).
String eventShareUrl(String eventId) {
  final base = AppConfig.shareBaseUrl;
  return base.isEmpty ? eventId : '$base/?event=$eventId';
}

/// Open the share sheet for [event]. Tries the OS share sheet first (web), then offers a
/// Copy-link action that always works. Returns when the sheet is dismissed.
Future<void> showShareSheet(BuildContext context, EventRead event) async {
  final url = eventShareUrl(event.id);
  final messenger = ScaffoldMessenger.of(context);

  Future<void> copyLink() async {
    await Clipboard.setData(ClipboardData(text: url));
    messenger.showSnackBar(const SnackBar(content: Text('Link copied')));
  }

  if (!context.mounted) return;
  await showModalBottomSheet<void>(
    context: context,
    backgroundColor: Theme.of(context).colorScheme.surface,
    showDragHandle: true,
    builder: (sheetContext) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 4),
            child: Text(
              event.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(sheetContext).textTheme.titleMedium,
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
            child: Text(
              url,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(sheetContext).textTheme.bodySmall?.copyWith(
                    color: Theme.of(sheetContext).colorScheme.onSurfaceVariant,
                  ),
            ),
          ),
          ListTile(
            key: const Key('share-os'),
            leading: const Icon(Icons.ios_share),
            title: const Text('Share…'),
            onTap: () async {
              Navigator.of(sheetContext).pop();
              final shared = await nativeShare(
                title: event.title,
                text: event.title,
                url: url,
              );
              // No OS share sheet (most desktops) → fall back to copying the link.
              if (!shared) await copyLink();
            },
          ),
          ListTile(
            key: const Key('share-copy'),
            leading: const Icon(Icons.link),
            title: const Text('Copy link'),
            onTap: () async {
              Navigator.of(sheetContext).pop();
              await copyLink();
            },
          ),
          const SizedBox(height: 8),
        ],
      ),
    ),
  );
}
