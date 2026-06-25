/// Capture/pick a video clip from the user's device for upload.
///
/// On the **web** ([clip_source_web.dart]) this opens a native file input — `accept="video/*"`
/// with an optional `capture` hint so mobile browsers open the camera directly. Off the web
/// ([clip_source_stub.dart]) it is unsupported for now (a native `camera`/`file_picker` path
/// lands in a later Creator-Studio phase), so callers fall back to the source-URL field.
///
/// Both implementations expose the same surface: [canCaptureClip] and [captureClip].
library;

export 'clip_source_types.dart';
export 'clip_source_stub.dart' if (dart.library.js_interop) 'clip_source_web.dart';
