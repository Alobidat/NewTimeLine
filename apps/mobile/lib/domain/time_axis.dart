/// Maps the signed-year time axis to/from screen pixels, with pan + zoom math.
/// Pure Dart so the (error-prone) coordinate logic is unit-tested without a widget.
library;

import 'dart:math' as math;

/// A linear viewport over the year axis `[t0, t1]` rendered across `width` pixels.
class TimeAxis {
  const TimeAxis({required this.t0, required this.t1, required this.width});

  final double t0;
  final double t1;
  final double width;

  double get span => t1 - t0;

  /// Pixel x for a year value.
  double xForT(double t) => (t - t0) / span * width;

  /// Year value for a pixel x.
  double tForX(double x) => t0 + (x / width) * span;

  /// Pan the viewport by a pixel delta (drag). Positive dx scrolls content right
  /// (i.e. moves the viewport toward earlier years).
  TimeAxis panByPixels(double dx) {
    final dt = dx / width * span;
    return TimeAxis(t0: t0 - dt, t1: t1 - dt, width: width);
  }

  /// Zoom by `factor` (<1 zooms in, >1 zooms out) keeping the year under `focalX`
  /// pinned to the same pixel. Span is clamped to a sane range.
  TimeAxis zoomAt(double focalX, double factor) {
    final focalT = tForX(focalX);
    final frac = (focalX / width).clamp(0.0, 1.0);
    var newSpan = span * factor;
    newSpan = newSpan.clamp(_minSpanYears, _maxSpanYears);
    final newT0 = focalT - frac * newSpan;
    return TimeAxis(t0: newT0, t1: newT0 + newSpan, width: width);
  }

  TimeAxis withWidth(double w) => TimeAxis(t0: t0, t1: t1, width: w);

  /// ~1 day at the fine end; ~2× the age of the universe at the coarse end.
  static const double _minSpanYears = 1.0 / 365.0;
  static const double _maxSpanYears = 3.0e10;

  /// A "nice" tick step (years) for the current span, targeting ~`targetTicks` labels.
  double niceTickStep({int targetTicks = 6}) {
    final raw = span / targetTicks;
    final mag = math.pow(10, (math.log(raw) / math.ln10).floor()).toDouble();
    final norm = raw / mag; // 1..10
    final step = norm < 1.5
        ? 1.0
        : norm < 3.5
        ? 2.0
        : norm < 7.5
        ? 5.0
        : 10.0;
    return math.max(step * mag, _minSpanYears);
  }
}
