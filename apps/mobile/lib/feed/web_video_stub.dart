/// Non-web stub for [webVideoView]. Never called off the web (the caller guards on `kIsWeb`),
/// but it keeps the conditional import type-correct on mobile/desktop builds.
library;

import 'package:flutter/widgets.dart';

/// Returns a decorative full-bleed HTML `<video>` on web; unsupported elsewhere.
Widget webVideoView(String url, {required bool muted}) =>
    throw UnsupportedError('webVideoView is web-only');
