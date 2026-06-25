/// Shared health/status visuals.
library;

import 'package:flutter/material.dart';

/// Color for a component/run status token.
Color statusColor(String status) {
  switch (status) {
    case 'ok':
      return const Color(0xFF3FB950);
    case 'running':
      return const Color(0xFF2E7DF6);
    case 'stale':
      return const Color(0xFFD29922);
    case 'error':
      return const Color(0xFFE5534B);
    default: // never | unknown
      return const Color(0xFF8B949E);
  }
}

IconData statusIcon(String status) {
  switch (status) {
    case 'ok':
      return Icons.check_circle;
    case 'running':
      return Icons.autorenew;
    case 'stale':
      return Icons.schedule;
    case 'error':
      return Icons.error;
    default:
      return Icons.remove_circle_outline;
  }
}

/// Color for a severity level (orthogonal to status; used by the health dashboard).
Color levelColor(String level) {
  switch (level) {
    case 'warning':
      return const Color(0xFFD29922);
    case 'degraded':
      return const Color(0xFFDB6D28);
    case 'critical':
      return const Color(0xFFE5534B);
    default: // ok
      return const Color(0xFF3FB950);
  }
}

IconData levelIcon(String level) {
  switch (level) {
    case 'warning':
      return Icons.warning_amber;
    case 'degraded':
      return Icons.trending_down;
    case 'critical':
      return Icons.error;
    default:
      return Icons.check_circle;
  }
}

/// A small pill showing a severity level. Hidden by the caller when level == 'ok'.
class LevelBadge extends StatelessWidget {
  const LevelBadge({super.key, required this.level});
  final String level;

  @override
  Widget build(BuildContext context) {
    final c = levelColor(level);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(levelIcon(level), size: 12, color: c),
          const SizedBox(width: 4),
          Text(level, style: TextStyle(color: c, fontWeight: FontWeight.w700, fontSize: 11)),
        ],
      ),
    );
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final c = statusColor(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: c.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(statusIcon(status), size: 14, color: c),
          const SizedBox(width: 6),
          Text(status, style: TextStyle(color: c, fontWeight: FontWeight.w600, fontSize: 12)),
        ],
      ),
    );
  }
}
