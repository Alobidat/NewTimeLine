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
