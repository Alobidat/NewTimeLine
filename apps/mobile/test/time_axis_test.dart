import 'package:chronos_app/domain/time_axis.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const axis = TimeAxis(t0: 2000, t1: 2100, width: 1000);

  test('xForT / tForX are inverses', () {
    expect(axis.xForT(2000), closeTo(0, 1e-9));
    expect(axis.xForT(2100), closeTo(1000, 1e-9));
    expect(axis.xForT(2050), closeTo(500, 1e-9));
    expect(axis.tForX(500), closeTo(2050, 1e-9));
  });

  test('pan shifts the range opposite to drag direction', () {
    final panned = axis.panByPixels(100); // drag right by 10% of width
    expect(panned.t0, closeTo(1990, 1e-9));
    expect(panned.t1, closeTo(2090, 1e-9));
  });

  test('zoom keeps the focal year pinned under the cursor', () {
    final zoomed = axis.zoomAt(500, 0.5); // zoom in 2x around the centre
    expect(zoomed.span, closeTo(50, 1e-9));
    // The focal year (2050) stays at x=500 in the new axis.
    expect(zoomed.tForX(500), closeTo(2050, 1e-6));
  });

  test('zoom clamps span to sane bounds', () {
    final wayOut = axis.zoomAt(500, 1e9);
    expect(wayOut.span, lessThanOrEqualTo(3.0e10));
    final wayIn = axis.zoomAt(500, 1e-9);
    expect(wayIn.span, greaterThan(0));
  });

  test('niceTickStep returns a positive round-ish step', () {
    expect(axis.niceTickStep(), greaterThan(0));
    expect(
      const TimeAxis(t0: -1000000, t1: 2000, width: 1000).niceTickStep(),
      greaterThan(0),
    );
  });
}
