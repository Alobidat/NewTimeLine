/// In-app camera recorder facade (Creator Studio Phase 1).
///
/// [canRecordInApp] is true on the web (getUserMedia + MediaRecorder); [createRecorderController]
/// builds the platform recorder. Off the web both degrade to "unsupported" so callers fall back
/// to the device file picker ([clip_source.dart]).
library;

export 'recorder_controller.dart';
export 'recorder_stub.dart' if (dart.library.js_interop) 'recorder_web.dart';
