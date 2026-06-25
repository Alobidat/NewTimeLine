/// In-app camera recorder facade (Creator Studio Phase 1).
///
/// [canRecordInApp] is true where live recording works — the web (getUserMedia + MediaRecorder)
/// and native mobile (the `camera` plugin). [createRecorderController] builds the platform
/// recorder. Desktop/test platforms report unavailable, so callers fall back to the device file
/// picker ([clip_source.dart]). One native impl covers android + iOS; the web impl covers the
/// browser — both behind the shared [RecorderController] + [RecorderScreen].
library;

export 'recorder_controller.dart';
export 'recorder_native.dart' if (dart.library.js_interop) 'recorder_web.dart';
