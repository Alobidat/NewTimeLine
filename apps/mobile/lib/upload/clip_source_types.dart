/// A video clip the user captured from a camera or picked from their device, ready to upload.
library;

import 'dart:typed_data';

class PickedClip {
  const PickedClip({
    required this.bytes,
    required this.filename,
    required this.mime,
    this.durationS,
  });

  /// The raw clip bytes (handed straight to `ApiClient.upload(fileBytes: …)`).
  final Uint8List bytes;

  /// The original file name (drives the upload's filename + extension).
  final String filename;

  /// The clip's MIME type (e.g. `video/mp4`, `video/webm`) — tags the multipart part so the
  /// server accepts it (it gates on `video/*`).
  final String mime;

  /// Clip length in seconds when known (in-app recordings track it via the shutter timer) —
  /// lets the editor offer a trim window. Null for device-picked files we haven't measured.
  final double? durationS;

  /// Size in bytes, for a friendly "12.3 MB" label before upload.
  int get sizeBytes => bytes.length;

  PickedClip copyWith({double? durationS}) => PickedClip(
        bytes: bytes,
        filename: filename,
        mime: mime,
        durationS: durationS ?? this.durationS,
      );
}
