/// Renders the timeline: tick axis, event markers (points/bands by severity), and the
/// density "heatline" when the server returns buckets (zoomed-out view).
library;

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../domain/time_axis.dart';
import '../domain/time_format.dart';
import '../theme/severity.dart';
import 'timeline_layout.dart';

class TimelinePainter extends CustomPainter {
  TimelinePainter({
    required this.t0,
    required this.t1,
    required this.data,
    required this.selectedId,
    required this.gridColor,
    required this.labelColor,
  });

  final double t0;
  final double t1;
  final TimelineResponse? data;
  final String? selectedId;
  final Color gridColor;
  final Color labelColor;

  @override
  void paint(Canvas canvas, Size size) {
    final axis = TimeAxis(t0: t0, t1: t1, width: size.width);
    final base = baselineY(size);

    _drawTicks(canvas, size, axis, base);

    final d = data;
    if (d != null) {
      if (d.isBuckets) {
        _drawBuckets(canvas, size, axis, base, d.buckets);
      } else {
        _drawEvents(canvas, size, axis, d.events);
      }
    }

    // Baseline.
    canvas.drawLine(
      Offset(0, base),
      Offset(size.width, base),
      Paint()
        ..color = labelColor.withValues(alpha: 0.6)
        ..strokeWidth = 1.2,
    );
  }

  void _drawTicks(Canvas canvas, Size size, TimeAxis axis, double base) {
    final step = axis.niceTickStep();
    final gridPaint = Paint()
      ..color = gridColor
      ..strokeWidth = 1;
    var t = (t0 / step).ceilToDouble() * step;
    var guard = 0;
    while (t <= t1 && guard++ < 200) {
      final x = axis.xForT(t);
      canvas.drawLine(Offset(x, 0), Offset(x, base), gridPaint);
      _label(canvas, formatYear(t), Offset(x + 3, base + 6));
      t += step;
    }
  }

  void _drawEvents(
    Canvas canvas,
    Size size,
    TimeAxis axis,
    List<EventRead> events,
  ) {
    final markers = layoutEvents(axis, size, events);
    final base = baselineY(size);
    for (final m in markers) {
      final color = severityColor(m.event.severity);
      final selected = m.event.id == selectedId;
      final stem = Paint()
        ..color = color.withValues(alpha: 0.55)
        ..strokeWidth = selected ? 2.5 : 1.3;
      canvas.drawLine(Offset(m.x, base), Offset(m.x, m.topY), stem);

      // Span bar for events with visible duration.
      final w = m.endX - m.x;
      if (w > 3) {
        canvas.drawRect(
          Rect.fromLTWH(m.x, m.topY - 2, w, 4),
          Paint()..color = color.withValues(alpha: 0.7),
        );
      }

      final dot = Paint()..color = color;
      canvas.drawCircle(Offset(m.x, m.topY), selected ? 6 : 4, dot);
      if (selected) {
        canvas.drawCircle(
          Offset(m.x, m.topY),
          8,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2
            ..color = Colors.white,
        );
      }
    }
  }

  void _drawBuckets(
    Canvas canvas,
    Size size,
    TimeAxis axis,
    double base,
    List<TimelineBucket> buckets,
  ) {
    if (buckets.isEmpty) return;
    final maxCount = buckets
        .map((b) => b.count)
        .reduce((a, b) => a > b ? a : b);
    final maxBar = base - 12;
    for (final b in buckets) {
      final x0 = axis.xForT(b.tStart);
      final x1 = axis.xForT(b.tEnd);
      if (x1 < 0 || x0 > size.width) continue;
      final h = (b.count / maxCount) * maxBar;
      canvas.drawRect(
        Rect.fromLTRB(x0, base - h, x1 - 0.5, base),
        Paint()..color = severityColor(b.peakSeverity).withValues(alpha: 0.75),
      );
    }
  }

  void _label(Canvas canvas, String text, Offset at) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(color: labelColor, fontSize: 11),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, at);
  }

  @override
  bool shouldRepaint(covariant TimelinePainter old) =>
      old.t0 != t0 ||
      old.t1 != t1 ||
      old.data != data ||
      old.selectedId != selectedId;
}
