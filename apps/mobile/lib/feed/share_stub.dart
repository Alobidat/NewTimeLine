/// Off-web stub for [nativeShare]: no system share sheet is available without a native plugin
/// (e.g. share_plus), so callers fall back to copy-link. Returns false so the caller knows the
/// OS share sheet did not open. See [share_web.dart] for the Web Share API implementation.
library;

Future<bool> nativeShare({
  required String title,
  required String text,
  required String url,
}) async =>
    false;
