/// Non-web stub for [webVideoView]. Never called off the web (the caller guards on `kIsWeb`),
/// but it keeps the conditional import type-correct on mobile/desktop builds.
library;

import 'package:flutter/widgets.dart';

/// Returns a decorative full-bleed HTML `<video>` on web; unsupported elsewhere.
Widget webVideoView(String url, {required bool muted}) =>
    throw UnsupportedError('webVideoView is web-only');

/// Feed-wide mute notifier — web-only behaviour; inert off the web (native clips have their
/// own per-clip tap-to-unmute in `feed_clip_player.dart`). Kept here so the conditional import
/// type-checks on mobile/desktop builds.
final ValueNotifier<bool> feedMuted = ValueNotifier<bool>(true);

void setFeedMuted(bool muted) {}
