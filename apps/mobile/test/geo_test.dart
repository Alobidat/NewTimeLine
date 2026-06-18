import 'package:chronos_app/map/geo.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('bboxString orders as minLon,minLat,maxLon,maxLat', () {
    expect(
      bboxString(west: -10, south: -5, east: 20, north: 30),
      '-10.0,-5.0,20.0,30.0',
    );
  });

  test('bboxString clamps to valid WGS84 ranges', () {
    expect(
      bboxString(west: -200, south: -100, east: 200, north: 100),
      '-180.0,-90.0,180.0,90.0',
    );
  });
}
