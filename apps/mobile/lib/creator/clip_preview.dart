/// A playable preview of a not-yet-uploaded [PickedClip] for the editor (Creator Studio Phase 1).
///
/// Lets the user watch the clip while setting trim/speed, so editing is **visual** rather than
/// blind. Platform-split behind one facade (mirroring [recorder.dart] / [clip_source.dart]):
/// the web impl ([clip_preview_web.dart]) plays a blob-URL `<video controls>`; the native impl
/// ([clip_preview_io.dart]) writes the bytes to a temp file and plays it via `video_player`.
/// Both render the same [ClipPreview] widget and degrade to a film glyph when playback isn't
/// available (e.g. the test VM), so the editor never breaks.
library;

export 'clip_preview_io.dart' if (dart.library.js_interop) 'clip_preview_web.dart';
