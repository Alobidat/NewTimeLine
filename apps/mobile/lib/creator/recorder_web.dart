/// Web recorder: live preview via getUserMedia, capture via MediaRecorder.
///
/// A `<video>` platform view is bound to the camera [MediaStream] for the preview; MediaRecorder
/// records the same stream into Blob chunks that are concatenated and read into bytes on stop.
/// All interop is defensive — any failure (no API, denied permission, unsupported type) resolves
/// to "unavailable"/null so [RecorderScreen] shows the file-picker fallback instead of breaking.
library;

import 'dart:async';
import 'dart:js_interop';

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;
import 'dart:ui_web' as ui_web;

import 'recorder_controller.dart';

bool get canRecordInApp {
  // getUserMedia + MediaRecorder must both exist (older/locked-down browsers lack them).
  final md = web.window.navigator.mediaDevices;
  return md.isDefinedAndNotNull && web.MediaRecorder.isTypeSupported('video/webm');
}

RecorderController createRecorderController() => _WebRecorder();

// Distinct viewType per controller so each recorder owns its preview element.
int _seq = 0;

class _WebRecorder implements RecorderController {
  web.MediaStream? _stream;
  web.HTMLVideoElement? _video;
  web.MediaRecorder? _recorder;
  final List<web.Blob> _chunks = <web.Blob>[];
  String _mime = 'video/webm';
  bool _front = true;
  bool _recording = false;
  late final String _viewType = 'chronos-recorder-${_seq++}';
  bool _registered = false;

  @override
  bool get isRecording => _recording;

  @override
  bool get canSwitchCamera => true; // best-effort; switching is a no-op if only one camera exists

  @override
  Future<bool> initPreview({bool front = true}) async {
    _front = front;
    final stream = await _acquire(front);
    if (stream == null) return false;
    _stream = stream;
    _mime = _pickMime();
    final v = web.HTMLVideoElement()
      ..autoplay = true
      ..muted = true // preview must be muted (it's the user's own mic) to avoid feedback
      ..srcObject = stream;
    v.setAttribute('playsinline', 'true');
    v.style.setProperty('width', '100%');
    v.style.setProperty('height', '100%');
    v.style.setProperty('object-fit', 'cover');
    v.style.setProperty('background-color', 'black');
    _video = v;
    if (!_registered) {
      _registered = true;
      ui_web.platformViewRegistry.registerViewFactory(_viewType, (int _) => _video!);
    }
    return true;
  }

  Future<web.MediaStream?> _acquire(bool front) async {
    try {
      final constraints = web.MediaStreamConstraints(
        audio: true.toJS,
        video: web.MediaTrackConstraints(
          facingMode: (front ? 'user' : 'environment').toJS,
        ),
      );
      return await web.window.navigator.mediaDevices.getUserMedia(constraints).toDart;
    } catch (_) {
      return null; // permission denied / no camera / insecure context
    }
  }

  String _pickMime() {
    for (final m in const [
      'video/mp4',
      'video/webm;codecs=vp9,opus',
      'video/webm;codecs=vp8,opus',
      'video/webm',
    ]) {
      try {
        if (web.MediaRecorder.isTypeSupported(m)) return m;
      } catch (_) {
        // ignore and try the next candidate
      }
    }
    return 'video/webm';
  }

  @override
  Widget buildPreview() => HtmlElementView(viewType: _viewType);

  @override
  void startRecording() {
    final stream = _stream;
    if (stream == null || _recording) return;
    _chunks.clear();
    try {
      final rec = web.MediaRecorder(stream, web.MediaRecorderOptions(mimeType: _mime));
      rec.ondataavailable = ((web.BlobEvent e) {
        if (e.data.size > 0) _chunks.add(e.data);
      }).toJS;
      _recorder = rec;
      rec.start();
      _recording = true;
    } catch (_) {
      _recording = false;
    }
  }

  @override
  Future<PickedClip?> stopRecording() async {
    final rec = _recorder;
    if (rec == null || !_recording) return null;
    _recording = false;
    final done = Completer<void>();
    rec.onstop = ((web.Event _) => done.complete()).toJS;
    try {
      rec.stop();
    } catch (_) {
      return null;
    }
    await done.future;
    if (_chunks.isEmpty) return null;
    try {
      final blob = web.Blob(
        _chunks.toJS,
        web.BlobPropertyBag(type: _mime),
      );
      final buffer = await blob.arrayBuffer().toDart;
      final bytes = buffer.toDart.asUint8List();
      final ext = _mime.startsWith('video/mp4') ? 'mp4' : 'webm';
      // The mime may carry codecs (e.g. video/webm;codecs=vp9) — the server splits on ';'.
      return PickedClip(bytes: bytes, filename: 'recording.$ext', mime: _mime);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<bool> switchCamera() async {
    if (_recording) return false;
    final next = !_front;
    final stream = await _acquire(next);
    if (stream == null) return false;
    _stopTracks(_stream);
    _stream = stream;
    _front = next;
    _video?.srcObject = stream; // same element keeps the preview live
    return true;
  }

  void _stopTracks(web.MediaStream? stream) {
    if (stream == null) return;
    final tracks = stream.getTracks().toDart;
    for (final t in tracks) {
      try {
        t.stop();
      } catch (_) {
        // best-effort teardown
      }
    }
  }

  @override
  void dispose() {
    try {
      if (_recording) _recorder?.stop();
    } catch (_) {
      // ignore
    }
    _recording = false;
    _stopTracks(_stream);
    _stream = null;
    _video?.srcObject = null;
    _video = null;
  }
}
