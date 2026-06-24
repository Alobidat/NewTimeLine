/// A full-bleed HTML `<video>` for the web feed (`object-fit: contain`), or an unsupported stub
/// off the web. Callers guard with `kIsWeb`. See [web_video_web.dart] for why we bypass
/// `video_player` on the web.
library;

export 'web_video_stub.dart' if (dart.library.js_interop) 'web_video_web.dart';
