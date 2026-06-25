/// Platform-agnostic contract for the in-app camera recorder (Creator Studio Phase 1).
///
/// The web implementation ([recorder_web.dart]) drives getUserMedia + MediaRecorder; the
/// non-web stub ([recorder_stub.dart]) reports unavailable. The recorder UI ([RecorderScreen])
/// talks only to this interface, so it's fully testable with a fake controller.
library;

import 'package:flutter/widgets.dart';

import '../upload/clip_source_types.dart';

export '../upload/clip_source_types.dart' show PickedClip;

abstract class RecorderController {
  /// Acquire the camera (and mic) and prepare a live preview. Returns false when recording isn't
  /// possible — no API, permission denied, or no camera — so the UI can offer the file fallback.
  Future<bool> initPreview({bool front = true});

  /// The live camera preview widget; valid only after a successful [initPreview].
  Widget buildPreview();

  /// Whether the camera can be flipped (front/back) on this device.
  bool get canSwitchCamera;

  bool get isRecording;

  void startRecording();

  /// Stop recording and return the captured clip (null if nothing was recorded / it failed).
  Future<PickedClip?> stopRecording();

  /// Flip between front/back cameras (only meaningful while not recording).
  Future<bool> switchCamera();

  void dispose();
}
