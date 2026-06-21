/// Pre-buffering the next clips in the feed (FR-1.3: pre-buffer the next 2 videos for
/// zero-lag transitions). The visible player still renders one clip at a time (a platform-view
/// constraint on CanvasKit web — see [FeedClipPlayer]); this warms the *upcoming* clip urls in
/// the background so swapping to them starts from warm cache. Web warms via `<link
/// rel="prefetch">`; off the web it is a no-op (native `video_player` buffering is handled by
/// the player itself).
library;

export 'prefetch_stub.dart' if (dart.library.js_interop) 'prefetch_web.dart';
