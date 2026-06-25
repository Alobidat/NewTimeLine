/// Non-web stub for clip capture — unsupported until the native camera/file-picker phase.
/// Callers check [canCaptureClip] and fall back to the source-URL field when it's false.
library;

import 'clip_source_types.dart';

/// In-app clip capture isn't available on this platform yet.
bool get canCaptureClip => false;

/// No-op off the web — returns null so the caller keeps the URL path.
Future<PickedClip?> captureClip({bool fromCamera = false}) async => null;
