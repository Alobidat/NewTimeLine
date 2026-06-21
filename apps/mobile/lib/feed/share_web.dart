/// Web implementation of [nativeShare]: invoke the browser's Web Share API
/// (`navigator.share`) so the user gets the real OS share sheet on supported browsers
/// (mobile Safari/Chrome, some desktops). Where it is unsupported — most desktop browsers —
/// the call throws and we return false so the caller falls back to copy-link.
library;

import 'dart:js_interop';

import 'package:web/web.dart' as web;

Future<bool> nativeShare({
  required String title,
  required String text,
  required String url,
}) async {
  try {
    // `navigator.share` is undefined on unsupported browsers; calling it throws (caught below).
    // Must be triggered by a user gesture (our rail-tap qualifies).
    await web.window.navigator
        .share(web.ShareData(title: title, text: text, url: url))
        .toDart;
    return true;
  } catch (_) {
    // Unsupported, dismissed, or blocked — let the caller fall back to copy-link.
    return false;
  }
}
