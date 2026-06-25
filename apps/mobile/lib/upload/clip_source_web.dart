/// Web implementation of clip capture: a hidden `<input type="file" accept="video/*">`.
///
/// With `capture="environment"` the input asks mobile browsers to open the **camera/camcorder**
/// directly; on desktop the attribute is ignored and a normal file chooser appears. The selected
/// file is read into bytes via `FileReader.readAsArrayBuffer` and returned as a [PickedClip] for
/// `ApiClient.upload(fileBytes: …)`. This is the Phase-1 capture path; an in-app live recorder
/// with effects (getUserMedia + WebGL + MediaRecorder) is a later Creator-Studio phase.
library;

import 'dart:async';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

import 'clip_source_types.dart';

bool get canCaptureClip => true;

Future<PickedClip?> captureClip({bool fromCamera = false}) async {
  final input = web.document.createElement('input') as web.HTMLInputElement;
  input.type = 'file';
  input.accept = 'video/*';
  if (fromCamera) {
    // Hint mobile browsers to open the camera rather than the gallery/file system.
    input.setAttribute('capture', 'environment');
  }
  input.style.setProperty('display', 'none');
  web.document.body?.appendChild(input);

  final completer = Completer<PickedClip?>();
  void finish(PickedClip? clip) {
    if (!completer.isCompleted) completer.complete(clip);
    input.remove();
  }

  input.onchange = ((web.Event _) {
    final files = input.files;
    final file = (files != null && files.length > 0) ? files.item(0) : null;
    if (file == null) {
      finish(null);
      return;
    }
    final reader = web.FileReader();
    reader.onload = ((web.Event _) {
      final result = reader.result;
      if (result != null && result.isA<JSArrayBuffer>()) {
        final bytes = (result as JSArrayBuffer).toDart.asUint8List();
        final mime = file.type.isNotEmpty ? file.type : 'video/mp4';
        finish(PickedClip(bytes: bytes, filename: file.name, mime: mime));
      } else {
        finish(null);
      }
    }).toJS;
    reader.onerror = ((web.Event _) => finish(null)).toJS;
    reader.readAsArrayBuffer(file);
  }).toJS;

  // Most browsers fire 'cancel' when the chooser is dismissed — don't leak a pending future.
  input.addEventListener('cancel', ((web.Event _) => finish(null)).toJS);

  input.click();
  return completer.future;
}
