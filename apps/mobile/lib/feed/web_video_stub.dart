/// Non-web stub for [webVideoView]. Never called off the web (the caller guards on `kIsWeb`),
/// but it keeps the conditional import type-correct on mobile/desktop builds.
library;

import 'package:flutter/widgets.dart';

/// A swipe gesture detected directly on the web `<video>` element: total travel ([dx], [dy])
/// and release velocity ([vx], [vy]) in logical px / px-per-second. Web-only; off the web the
/// feed's Flutter [GestureDetector] handles swipes instead, so this never fires.
typedef WebSwipe = void Function(double dx, double dy, double vx, double vy);

/// Returns a raw HTML `<video>` view on web; unsupported elsewhere.
Widget webVideoView(String url, {required bool muted, WebSwipe? onSwipe}) =>
    throw UnsupportedError('webVideoView is web-only');
