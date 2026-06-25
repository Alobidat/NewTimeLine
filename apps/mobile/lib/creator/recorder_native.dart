/// Native (android/iOS) in-app recorder via the `camera` plugin — the parity counterpart of the
/// web getUserMedia/MediaRecorder recorder. Same [RecorderController] contract + same
/// [RecorderScreen] UI; only this binding differs. One impl covers android and iOS.
///
/// Defensive throughout: no camera / denied permission / init failure resolves to
/// unavailable/null so the screen offers the file-picker fallback instead of breaking.
library;

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'recorder_controller.dart';

/// In-app recording is available on real mobile devices (android/iOS). Desktop/test platforms
/// fall back to the file picker. Actual camera availability is confirmed by [initPreview].
bool get canRecordInApp =>
    !kIsWeb &&
    (defaultTargetPlatform == TargetPlatform.android ||
        defaultTargetPlatform == TargetPlatform.iOS);

RecorderController createRecorderController() => _NativeRecorder();

class _NativeRecorder implements RecorderController {
  List<CameraDescription> _cameras = const [];
  CameraController? _controller;
  bool _front = true;
  bool _recording = false;

  @override
  bool get isRecording => _recording;

  @override
  bool get canSwitchCamera => _cameras.length > 1;

  @override
  Future<bool> initPreview({bool front = true}) async {
    _front = front;
    try {
      _cameras = await availableCameras();
      if (_cameras.isEmpty) return false;
      return _open(front);
    } catch (_) {
      return false; // no permission / no camera / platform error → file fallback
    }
  }

  Future<bool> _open(bool front) async {
    try {
      final controller = CameraController(
        _pick(front),
        ResolutionPreset.high,
        enableAudio: true,
      );
      await controller.initialize();
      _controller = controller;
      _front = front;
      return true;
    } catch (_) {
      return false;
    }
  }

  CameraDescription _pick(bool front) {
    final dir = front ? CameraLensDirection.front : CameraLensDirection.back;
    return _cameras.firstWhere(
      (c) => c.lensDirection == dir,
      orElse: () => _cameras.first,
    );
  }

  @override
  Widget buildPreview() {
    final c = _controller;
    if (c == null || !c.value.isInitialized) {
      return const ColoredBox(color: Color(0xFF000000));
    }
    return CameraPreview(c);
  }

  @override
  void startRecording() {
    final c = _controller;
    if (c == null || _recording) return;
    _recording = true;
    // Fire-and-forget to match the sync interface (web's MediaRecorder.start() is sync too);
    // a failure flips the flag back so stop() is a no-op.
    c.startVideoRecording().catchError((_) {
      _recording = false;
    });
  }

  @override
  Future<PickedClip?> stopRecording() async {
    final c = _controller;
    if (c == null || !_recording) return null;
    _recording = false;
    try {
      final file = await c.stopVideoRecording();
      final bytes = await file.readAsBytes();
      final name = file.name.isNotEmpty ? file.name : 'recording.mp4';
      final mime = name.toLowerCase().endsWith('.mov') ? 'video/quicktime' : 'video/mp4';
      return PickedClip(bytes: bytes, filename: name, mime: mime);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<bool> switchCamera() async {
    if (_recording || _cameras.length < 2) return false;
    final next = !_front;
    await _controller?.dispose();
    _controller = null;
    return _open(next);
  }

  @override
  void dispose() {
    _controller?.dispose();
    _controller = null;
  }
}
