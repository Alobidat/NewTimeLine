/// The magical timeline screen: scrub (drag), zoom (pinch / mouse wheel), tap an event
/// to open its detail + sub-timeline. Anonymous — no account needed (ADR-0007).
library;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../domain/time_axis.dart';
import '../domain/time_format.dart';
import '../event/event_detail_sheet.dart';
import 'timeline_controller.dart';
import 'timeline_layout.dart';
import 'timeline_painter.dart';

class TimelineScreen extends StatefulWidget {
  const TimelineScreen({super.key});

  @override
  State<TimelineScreen> createState() => _TimelineScreenState();
}

class _TimelineScreenState extends State<TimelineScreen> {
  final TimelineController _c = TimelineController();
  Size _size = Size.zero;
  double _lastScale = 1.0;
  String? _selectedId;

  // Quick-jump presets across the whole axis.
  static const _presets = <(String, double, double)>[
    ('Deep time', -1000000, 2030),
    ('Antiquity', -3000, 600),
    ('Last century', 1925, 2030),
    ('Live', 2024, 2027),
  ];

  @override
  void initState() {
    super.initState();
    _c.reload();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  TimeAxis get _axis => TimeAxis(t0: _c.t0, t1: _c.t1, width: _size.width);

  void _onScaleStart(ScaleStartDetails d) => _lastScale = 1.0;

  void _onScaleUpdate(ScaleUpdateDetails d) {
    if (_size.width <= 0) return;
    var axis = _axis.panByPixels(d.focalPointDelta.dx);
    final scaleDelta = d.scale / _lastScale;
    _lastScale = d.scale;
    if ((scaleDelta - 1).abs() > 1e-3) {
      axis = axis.zoomAt(d.localFocalPoint.dx, 1 / scaleDelta);
    }
    _c.setRange(axis.t0, axis.t1);
  }

  void _onPointerSignal(PointerSignalEvent e) {
    if (e is PointerScrollEvent && _size.width > 0) {
      final factor = e.scrollDelta.dy > 0 ? 1.15 : 1 / 1.15;
      final axis = _axis.zoomAt(e.localPosition.dx, factor);
      _c.setRange(axis.t0, axis.t1);
    }
  }

  void _onTapUp(TapUpDetails d) {
    final data = _c.data;
    // Can't tap individual events when the view is bucketed (zoomed out).
    if (data == null || data.isBuckets) {
      return;
    }
    final markers = layoutEvents(_axis, _size, data.events);
    final hit = hitTest(markers, d.localPosition);
    if (hit != null) {
      setState(() => _selectedId = hit.id);
      showEventDetail(context, _c, hit.id);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Chronos — Timeline'),
        actions: [
          IconButton(
            tooltip: 'Reload',
            onPressed: _c.reload,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
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
                      builder: (context, _) => Stack(
                        children: [
                          Positioned.fill(
                            child: CustomPaint(
                              painter: TimelinePainter(
                                t0: _c.t0,
                                t1: _c.t1,
                                data: _c.data,
                                selectedId: _selectedId,
                                gridColor: scheme.outlineVariant.withValues(
                                  alpha: 0.25,
                                ),
                                labelColor: scheme.onSurfaceVariant,
                              ),
                            ),
                          ),
                          if (_c.loading)
                            const Positioned(
                              top: 8,
                              right: 8,
                              child: SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              ),
                            ),
                          Positioned(
                            left: 12,
                            top: 12,
                            child: _RangeLabel(_c.t0, _c.t1, _c.data?.mode),
                          ),
                          if (_c.error != null)
                            Positioned(
                              left: 12,
                              right: 12,
                              bottom: 12,
                              child: _Banner(
                                'API error: ${_c.error}',
                                scheme.error,
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          _PresetBar(onSelect: (a, b) => _c.setRange(a, b)),
        ],
      ),
    );
  }
}

class _PresetBar extends StatelessWidget {
  const _PresetBar({required this.onSelect});
  final void Function(double t0, double t1) onSelect;

  @override
  Widget build(BuildContext context) => SafeArea(
    top: false,
    child: SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: [
          for (final p in _TimelineScreenState._presets)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ActionChip(
                label: Text(p.$1),
                onPressed: () => onSelect(p.$2, p.$3),
              ),
            ),
        ],
      ),
    ),
  );
}

class _RangeLabel extends StatelessWidget {
  const _RangeLabel(this.t0, this.t1, this.mode);
  final double t0;
  final double t1;
  final String? mode;
  @override
  Widget build(BuildContext context) {
    final modeTag = mode == 'buckets' ? '  ·  heatline' : '';
    return IgnorePointer(
      child: Text(
        '${formatYear(t0)} → ${formatYear(t1)}$modeTag',
        style: Theme.of(context).textTheme.labelLarge,
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner(this.text, this.color);
  final String text;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.15),
      borderRadius: BorderRadius.circular(6),
    ),
    child: Text(text, style: TextStyle(color: color)),
  );
}
