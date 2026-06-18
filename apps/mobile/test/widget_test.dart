// Network-free smoke test: the timeline painter renders with no data (default range)
// without throwing. Full UI flows are exercised manually against the live API.

import 'package:chronos_app/timeline/timeline_painter.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('TimelinePainter paints empty state without error', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CustomPaint(
            size: const Size(800, 400),
            painter: TimelinePainter(
              t0: 1900,
              t1: 2030,
              data: null,
              selectedId: null,
              gridColor: const Color(0x22FFFFFF),
              labelColor: const Color(0xFFCCCCCC),
            ),
          ),
        ),
      ),
    );
    expect(find.byType(CustomPaint), findsWidgets);
  });
}
