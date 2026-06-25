/// Native (android/iOS/desktop) implementation of clip picking via `file_picker`.
///
/// Picks a video from the device's gallery/files and loads its bytes for upload. "Record"
/// (camera) is handled by the in-app recorder ([recorder_native.dart]) on native, so this only
/// covers the "Choose" path — the same shared [PickedClip] the web file path returns.
library;

import 'package:file_picker/file_picker.dart';

import 'clip_source_types.dart';

bool get canCaptureClip => true;

Future<PickedClip?> captureClip({bool fromCamera = false}) async {
  final result = await FilePicker.platform.pickFiles(
    type: FileType.video,
    withData: true, // load bytes so we can hand them straight to ApiClient.upload
  );
  if (result == null || result.files.isEmpty) return null;
  final file = result.files.first;
  final bytes = file.bytes;
  if (bytes == null) return null;
  return PickedClip(bytes: bytes, filename: file.name, mime: _mimeFor(file.extension));
}

String _mimeFor(String? ext) {
  switch ((ext ?? '').toLowerCase()) {
    case 'mp4':
    case 'm4v':
      return 'video/mp4';
    case 'mov':
      return 'video/quicktime';
    case 'webm':
      return 'video/webm';
    case 'ogv':
      return 'video/ogg';
    default:
      return 'video/mp4';
  }
}
