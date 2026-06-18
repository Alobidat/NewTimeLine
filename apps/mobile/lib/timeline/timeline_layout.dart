/// Pure layout + hit-testing for timeline event markers (shared by the painter and
/// the screen's tap handling, and unit-tested without a widget).
library;

import 'dart:ui';

import '../api/models.dart';
import '../domain/time_axis.dart';

/// Vertical room reserved below the baseline for tick labels.
const double kAxisLabelGap = 28.0;

/// A laid-out event: its anchor x, the bar end x (for spans), and bar-top y.
class EventMarker {
  EventMarker(this.event, this.x, this.endX, this.topY);
  final EventRead event;
  final double x; // x of t_start
  final double endX; // x of t_end (== x for instantaneous)
  final double topY; // top of the severity bar
}

double baselineY(Size size) => size.height - kAxisLabelGap;

/// Lay out events against the axis/size. Severity drives bar height.
List<EventMarker> layoutEvents(
  TimeAxis axis,
  Size size,
  List<EventRead> events,
) {
  final base = baselineY(size);
  final maxBar = (base - 12).clamp(8.0, size.height);
  final markers = <EventMarker>[];
  for (final e in events) {
    final x = axis.xForT(e.tStart);
    if (x < -40 || x > size.width + 40) continue; // cull offscreen
    final h = (e.severity.clamp(0, 100) / 100.0) * maxBar;
    markers.add(EventMarker(e, x, axis.xForT(e.tEnd), base - (h < 6 ? 6 : h)));
  }
  return markers;
}

/// Nearest marker to a tap, by horizontal distance, within [threshold] px.
EventRead? hitTest(
  List<EventMarker> markers,
  Offset tap, {
  double threshold = 16,
}) {
  EventRead? best;
  var bestDx = threshold;
  for (final m in markers) {
    final dx = (m.x - tap.dx).abs();
    if (dx <= bestDx) {
      bestDx = dx;
      best = m.event;
    }
  }
  return best;
}
