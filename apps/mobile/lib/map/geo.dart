/// Pure geo helpers for the map layer (unit-tested without a widget).
library;

/// Format a viewport as the API's bbox string "minLon,minLat,maxLon,maxLat",
/// clamped to valid WGS84 ranges (web maps can report slightly out-of-range edges).
String bboxString({
  required double west,
  required double south,
  required double east,
  required double north,
}) {
  final w = west.clamp(-180.0, 180.0);
  final e = east.clamp(-180.0, 180.0);
  final s = south.clamp(-90.0, 90.0);
  final n = north.clamp(-90.0, 90.0);
  return '$w,$s,$e,$n';
}
