/// Non-web stub: in-app recording isn't available (the camera path is web-only for now). A
/// native recorder lands in a later Creator-Studio phase. Callers fall back to the file picker.
library;

import 'package:flutter/widgets.dart';

import 'recorder_controller.dart';

bool get canRecordInApp => false;

RecorderController createRecorderController() => _UnsupportedRecorder();

class _UnsupportedRecorder implements RecorderController {
  @override
  Future<bool> initPreview({bool front = true}) async => false;

  @override
  Widget buildPreview() => const SizedBox.shrink();

  @override
  bool get canSwitchCamera => false;

  @override
  bool get isRecording => false;

  @override
  void startRecording() {}

  @override
  Future<PickedClip?> stopRecording() async => null;

  @override
  Future<bool> switchCamera() async => false;

  @override
  void dispose() {}
}
