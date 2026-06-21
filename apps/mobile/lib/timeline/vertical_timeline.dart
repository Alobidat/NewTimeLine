/// The timeline as a vertical scroll/zoom bar pinned to the right edge. Drag it up/down to
/// scroll through time; pinch or mouse-wheel to zoom (ms → millennia). The whole bar is the
/// current visible range — year labels along it are the range indicator — and it shows the
/// density heatline (zoomed out) or event ticks (zoomed in). Tapping an event focuses it.
///
/// Reuses the same [TimeAxis] math as the horizontal timeline, just with the bar's *height*
/// as the axis extent, so pan/zoom behave identically.
library;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../api/models.dart';
import '../domain/time_axis.dart';
import '../domain/time_format.dart';
import '../theme/severity.dart';
import 'timeline_controller.dart';

const double _gutter = 40.0; // left strip for year labels

class VerticalTimelineBar extends StatefulWidget {
  const VerticalTimelineBar({
    super.key,
    required this.controller,
    this.onEventTap,
    this.selectedId,
    this.width = 88,
  });

  final TimelineController controller;
  final void Function(String id)? onEventTap;
  final String? selectedId;
  final double width;

  @override
  State<VerticalTimelineBar> createState() => _VerticalTimelineBarState();
}

class _VerticalTimelineBarState extends State<VerticalTimelineBar> {
  TimelineController get _c => widget.controller;
  Size _size = Size.zero;
  double _lastScale = 1.0;

  TimeAxis _axis(double extent) =>
      TimeAxis(t0: _c.t0, t1: _c.t1, width: extent);

  void _onScaleStart(ScaleStartDetails _) => _lastScale = 1.0;

  void _onScaleUpdate(ScaleUpdateDetails d) {
    final h = _size.height;
    if (h <= 0) return;
    var axis = _axis(h).panByPixels(d.focalPointDelta.dy); // drag = scroll time
    final scaleDelta = d.scale / _lastScale;
    _lastScale = d.scale;
    if ((scaleDelta - 1).abs() > 1e-3) {
      axis = axis.zoomAt(d.localFocalPoint.dy, 1 / scaleDelta); // pinch = zoom
    }
    _c.setRange(axis.t0, axis.t1);
  }

  void _onPointerSignal(PointerSignalEvent e) {
    if (e is PointerScrollEvent && _size.height > 0) {
      final factor = e.scrollDelta.dy > 0 ? 1.15 : 1 / 1.15; // wheel = zoom
      final axis = _axis(_size.height).zoomAt(e.localPosition.dy, factor);
      _c.setRange(axis.t0, axis.t1);
    }
  }

  void _onTapUp(TapUpDetails d) {
    final data = _c.data;
    if (data == null || data.isBuckets || _size.height <= 0) return;
    final axis = _axis(_size.height);
    EventRead? best;
    var bestDy = 18.0;
    for (final e in data.events) {
      final dy = (axis.xForT(e.tStart) - d.localPosition.dy).abs();
      if (dy <= bestDy) {
        bestDy = dy;
        best = e;
      }
    }
    if (best != null) widget.onEventTap?.call(best.id);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      width: widget.width,
      child: Material(
        color: scheme.surface.withValues(alpha: 0.92),
        child: LayoutBuilder(
          builder: (context, constraints) {
            _size = Size(constraints.maxWidth, constraints.maxHeight);
            return Listener(
              onPointerSignal: _onPointerSignal,
              child: GestureDetector(
                onScaleStart: _onScaleStart,
                onScaleUpdate: _onScaleUpdate,
                onTapUp: _onTapUp,
                child: AnimatedBuilder(
                  animation: _c,
                  builder: (context, _) => CustomPaint(
                    size: Size.infinite,
                    painter: _VerticalPainter(
                      t0: _c.t0,
                      t1: _c.t1,
                      data: _c.data,
                      selectedId: widget.selectedId,
                      gridColor: scheme.outlineVariant.withValues(alpha: 0.25),
                      labelColor: scheme.onSurfaceVariant,
                      accent: scheme.primary,
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _VerticalPainter extends CustomPainter {
  _VerticalPainter({
    required this.t0,
    required this.t1,
    required this.data,
    required this.selectedId,
    required this.gridColor,
    required this.labelColor,
    required this.accent,
  });

  final double t0;
  final double t1;
  final TimelineResponse? data;
  final String? selectedId;
  final Color gridColor;
  final Color labelColor;
  final Color accent;

  @override
  void paint(Canvas canvas, Size size) {
    final axis = TimeAxis(t0: t0, t1: t1, width: size.height);

    // The spine the bars/events grow from.
    canvas.drawLine(
      Offset(_gutter, 0),
      Offset(_gutter, size.height),
      Paint()
        ..color = labelColor.withValues(alpha: 0.5)
        ..strokeWidth = 1.2,
    );

    _drawTicks(canvas, size, axis);

    final d = data;
    if (d != null) {
      if (d.isBuckets) {
        _drawBuckets(canvas, size, axis, d.buckets);
      } else {
        _drawEvents(canvas, size, axis, d.events);
      }
    }
  }

  void _drawTicks(Canvas canvas, Size size, TimeAxis axis) {
    final step = axis.niceTickStep(targetTicks: (size.height / 70).clamp(3, 12).toInt());
    final grid = Paint()
      ..color = gridColor
      ..strokeWidth = 1;
    var t = (t0 / step).ceilToDouble() * step;
    var guard = 0;
    while (t <= t1 && guard++ < 200) {
      final y = axis.xForT(t);
      canvas.drawLine(Offset(_gutter - 4, y), Offset(_gutter, y), grid);
      _label(canvas, formatYear(t), 4, y - 6, labelColor, 10);
      t += step;
    }
  }

  void _drawBuckets(
    Canvas canvas,
    Size size,
    TimeAxis axis,
    List<TimelineBucket> buckets,
  ) {
    if (buckets.isEmpty) return;
    final maxCount = buckets.map((b) => b.count).reduce((a, b) => a > b ? a : b);
    final maxLen = size.width - _gutter - 6;
    for (final b in buckets) {
      final y0 = axis.xForT(b.tStart);
      final y1 = axis.xForT(b.tEnd);
      if (y1 < 0 || y0 > size.height) continue;
      final len = (b.count / maxCount) * maxLen;
      canvas.drawRect(
        Rect.fromLTRB(_gutter, y0, _gutter + len, y1 - 0.5),
        Paint()..color = severityColor(b.peakSeverity).withValues(alpha: 0.78),
      );
    }
  }

  void _drawEvents(
    Canvas canvas,
    Size size,
    TimeAxis axis,
    List<EventRead> events,
  ) {
    final maxLen = size.width - _gutter - 14;
    for (final e in events) {
      final y = axis.xForT(e.tStart);
      if (y < -20 || y > size.height + 20) continue;
      final color = severityColor(e.severity);
      final selected = e.id == selectedId;
      final len = (e.severity.clamp(0, 100) / 100.0) * maxLen;
      final dotX = _gutter + (len < 8 ? 8 : len);
      canvas.drawLine(
        Offset(_gutter, y),
        Offset(dotX, y),
        Paint()
          ..color = color.withValues(alpha: 0.55)
          ..strokeWidth = selected ? 2.5 : 1.3,
      );
      canvas.drawCircle(Offset(dotX, y), selected ? 6 : 4, Paint()..color = color);
      if (selected) {
        canvas.drawCircle(
          Offset(dotX, y),
          8,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2
            ..color = Colors.white,
        );
      }
    }
  }

  void _label(Canvas canvas, String text, double x, double y, Color color, double size) {
    final tp = TextPainter(
      text: TextSpan(text: text, style: TextStyle(color: color, fontSize: size)),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset(x, y));
  }

  @override
  bool shouldRepaint(covariant _VerticalPainter old) =>
      old.t0 != t0 ||
      old.t1 != t1 ||
      old.data != data ||
      old.selectedId != selectedId;
}
