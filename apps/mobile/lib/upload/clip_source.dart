/// Capture/pick a video clip from the user's device for upload.
///
/// On the **web** ([clip_source_web.dart]) this opens a native file input — `accept="video/*"`
/// with an optional `capture` hint so mobile browsers open the camera directly. On **native**
/// ([clip_source_io.dart]) it uses `file_picker` to choose a video from the device. One impl
/// serves android + iOS + desktop; the web impl serves the browser.
///
/// Both implementations expose the same surface: [canCaptureClip] and [captureClip].
library;

export 'clip_source_types.dart';
export 'clip_source_io.dart' if (dart.library.js_interop) 'clip_source_web.dart';
