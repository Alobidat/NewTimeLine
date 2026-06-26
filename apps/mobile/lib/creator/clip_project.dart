/// Pure, platform-agnostic edit a user makes to a clip before publishing (Creator Studio
/// Phase 1 — the "edit" of capture→edit→publish): an optional **trim** window and a **speed**.
///
/// This carries no Flutter/IO — it's the client mirror of the backend's `normalize_edit_spec`
/// (`chronos_core.domain.media_edit`), so the values the UI shows and the values the server
/// applies agree. The screen edits a [ClipProject] and hands its [uploadTrimStart] /
/// [uploadTrimEnd] / [uploadSpeed] to `ApiClient.upload`; the transcode agent does the rest.
library;

import 'package:flutter/foundation.dart';

@immutable
class ClipProject {
  const ClipProject({
    this.trimStart,
    this.trimEnd,
    this.speed = 1.0,
    this.durationS,
  });

  /// Trim window in seconds (null = no bound). Times outside the clip are normalized away.
  final double? trimStart;
  final double? trimEnd;

  /// Playback speed multiplier; 1.0 = unchanged. Clamped to [minSpeed]–[maxSpeed] on export.
  final double speed;

  /// Source clip duration in seconds when known (in-app recordings) — enables the trim UI.
  /// Null for device-picked files whose length we haven't measured; speed still works.
  final double? durationS;

  /// ffmpeg's atempo handles 0.5–2.0 in one pass; matches the backend's MIN/MAX_SPEED.
  static const double minSpeed = 0.5;
  static const double maxSpeed = 2.0;

  ClipProject copyWith({
    double? trimStart,
    double? trimEnd,
    double? speed,
    double? durationS,
    bool clearTrimStart = false,
    bool clearTrimEnd = false,
  }) {
    return ClipProject(
      trimStart: clearTrimStart ? null : (trimStart ?? this.trimStart),
      trimEnd: clearTrimEnd ? null : (trimEnd ?? this.trimEnd),
      speed: speed ?? this.speed,
      durationS: durationS ?? this.durationS,
    );
  }

  static double _round3(double x) => (x * 1000).round() / 1000;

  /// The normalized trim window, dropping no-ops and any end-not-after-start window — exactly
  /// the backend's rule, so a window the UI considers valid is the window the server applies.
  ({double? start, double? end}) get _trim {
    double? s = (trimStart != null && trimStart! > 0) ? _round3(trimStart!) : null;
    double? e = (trimEnd != null && trimEnd! > 0) ? _round3(trimEnd!) : null;
    if (e != null && e <= (s ?? 0)) {
      s = null;
      e = null; // not a usable window → drop the trim (speed is unaffected)
    }
    return (start: s, end: e);
  }

  /// Trim start to send with the upload (null when there's no effective lower bound).
  double? get uploadTrimStart => _trim.start;

  /// Trim end to send with the upload (null when there's no effective upper bound).
  double? get uploadTrimEnd => _trim.end;

  /// Speed to send with the upload — clamped, and null when it's a no-op (1.0).
  double? get uploadSpeed {
    if (speed <= 0) return null;
    final c = _round3(speed.clamp(minSpeed, maxSpeed).toDouble());
    return c == 1.0 ? null : c;
  }

  /// Whether this project changes anything (drives "Edited" affordances + whether to send params).
  bool get hasEdits =>
      uploadTrimStart != null || uploadTrimEnd != null || uploadSpeed != null;

  /// Whether a trim UI can be offered (we need the clip's length to bound the slider).
  bool get canTrim => durationS != null && durationS! > 0;

  @override
  bool operator ==(Object other) =>
      other is ClipProject &&
      other.trimStart == trimStart &&
      other.trimEnd == trimEnd &&
      other.speed == speed &&
      other.durationS == durationS;

  @override
  int get hashCode => Object.hash(trimStart, trimEnd, speed, durationS);
}
