/// Compact resource gauges for the System Health dashboard — a labelled bar whose fill and
/// colour reflect utilization against warning/critical thresholds. No charting dependency.
library;

import 'package:flutter/material.dart';

/// Colour a 0..1 utilization fraction green/amber/red against thresholds.
Color gaugeColor(double fraction, {double warning = 0.80, double critical = 0.92}) {
  if (fraction >= critical) return const Color(0xFFE5534B);
  if (fraction >= warning) return const Color(0xFFD29922);
  return const Color(0xFF3FB950);
}

/// A labelled horizontal bar gauge. When [fraction] is null only [valueText] is shown
/// (for non-percentage metrics like load average).
class MetricGauge extends StatelessWidget {
  const MetricGauge({
    super.key,
    required this.label,
    required this.valueText,
    this.fraction,
    this.icon,
    this.warning = 0.80,
    this.critical = 0.92,
  });

  final String label;
  final String valueText;
  final double? fraction; // 0..1, drives the bar fill + colour
  final IconData? icon;
  final double warning;
  final double critical;

  @override
  Widget build(BuildContext context) {
    final f = fraction?.clamp(0.0, 1.0);
    final c = f == null ? const Color(0xFF2E7DF6) : gaugeColor(f, warning: warning, critical: critical);
    return SizedBox(
      width: 200,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (icon != null) ...[Icon(icon, size: 14, color: c), const SizedBox(width: 6)],
              Text(label, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12)),
              const Spacer(),
              Text(valueText, style: TextStyle(color: c, fontWeight: FontWeight.w700, fontSize: 13)),
            ],
          ),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: f,
              minHeight: 8,
              backgroundColor: c.withValues(alpha: 0.15),
              valueColor: AlwaysStoppedAnimation(c),
            ),
          ),
        ],
      ),
    );
  }
}
