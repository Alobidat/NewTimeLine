/// Severity → colour mapping for the timeline/map (calm blue → urgent red).
library;

import 'package:flutter/material.dart';

const Color _calm = Color(0xFF2E7DF6); // blue, low severity
const Color _urgent = Color(0xFFE53935); // red, high severity

/// Colour for a 0..100 severity score.
Color severityColor(int severity) {
  final t = (severity.clamp(0, 100)) / 100.0;
  return Color.lerp(_calm, _urgent, t)!;
}
