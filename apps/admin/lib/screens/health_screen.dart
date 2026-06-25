/// System Health dashboard — every component grouped by plane (edge/api/processing/store)
/// with live status + severity level, plus host resource gauges (CPU/memory/disk/load).
/// Polls /admin/health; tap any component to drill into its detail (logs + metrics).
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../widgets/gauge.dart';
import '../widgets/health.dart';
import '../widgets/polling.dart';

class HealthScreen extends StatelessWidget {
  const HealthScreen({super.key, required this.client, required this.onOpenComponent});

  final AdminClient client;
  final void Function(String componentId) onOpenComponent;

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<HealthTreeView>(
      fetch: client.health,
      interval: const Duration(seconds: 5),
      builder: (context, tree) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _SystemBanner(tree: tree),
          const SizedBox(height: 16),
          _HostCard(host: tree.host),
          const SizedBox(height: 8),
          for (final group in tree.planes) _PlaneSection(group: group, onTap: onOpenComponent),
        ],
      ),
    );
  }
}

class _SystemBanner extends StatelessWidget {
  const _SystemBanner({required this.tree});
  final HealthTreeView tree;

  @override
  Widget build(BuildContext context) {
    final c = levelColor(tree.level);
    final n = tree.planes.fold<int>(0, (sum, g) => sum + g.components.length);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: c.withValues(alpha: 0.5)),
      ),
      child: Row(
        children: [
          Icon(levelIcon(tree.level), color: c),
          const SizedBox(width: 12),
          Text('System ${tree.level.toUpperCase()}',
              style: TextStyle(color: c, fontWeight: FontWeight.w800, fontSize: 16)),
          const SizedBox(width: 12),
          Text('$n components · ${tree.planes.length} planes',
              style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _HostCard extends StatelessWidget {
  const _HostCard({required this.host});
  final HostMetricsView host;

  @override
  Widget build(BuildContext context) {
    final cpu = host['cpu_pct'];
    final mem = host['mem_used_pct'];
    final disk = host['disk_used_pct'];
    final load = host['load_1m'];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Host resources', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            Wrap(
              spacing: 24,
              runSpacing: 16,
              children: [
                if (cpu != null)
                  MetricGauge(label: 'CPU', icon: Icons.memory,
                      valueText: '${cpu.toStringAsFixed(1)}%', fraction: cpu / 100),
                if (mem != null)
                  MetricGauge(label: 'Memory', icon: Icons.straighten,
                      valueText: '${mem.toStringAsFixed(1)}%', fraction: mem / 100),
                if (disk != null)
                  MetricGauge(label: 'Storage', icon: Icons.save,
                      valueText: '${disk.toStringAsFixed(1)}%', fraction: disk / 100),
                if (load != null)
                  MetricGauge(label: 'Load (1m)', icon: Icons.speed,
                      valueText: load.toStringAsFixed(2)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _PlaneSection extends StatelessWidget {
  const _PlaneSection({required this.group, required this.onTap});
  final PlaneGroup group;
  final void Function(String componentId) onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 16, bottom: 8, left: 4),
          child: Row(
            children: [
              Text(group.plane.toUpperCase(),
                  style: const TextStyle(fontWeight: FontWeight.w800, letterSpacing: 0.5)),
              const SizedBox(width: 10),
              if (group.level != 'ok') LevelBadge(level: group.level),
              const SizedBox(width: 8),
              Text('${group.components.length}', style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            for (final c in group.components) _ComponentCard(component: c, onTap: onTap),
          ],
        ),
      ],
    );
  }
}

class _ComponentCard extends StatelessWidget {
  const _ComponentCard({required this.component, required this.onTap});
  final ComponentView component;
  final void Function(String componentId) onTap;

  @override
  Widget build(BuildContext context) {
    final h = component.health;
    final metrics = component.latestMetrics ?? const {};
    final chips = metrics.entries.take(3).map((e) => _metricChip(e.key, e.value)).toList();
    return SizedBox(
      width: 268,
      child: Card(
        margin: EdgeInsets.zero,
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => onTap(component.id),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(component.title,
                          maxLines: 1, overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                    ),
                    if (h.level != 'ok') LevelBadge(level: h.level),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    StatusChip(status: h.status),
                    const Spacer(),
                    if (component.enabled == false)
                      Text('disabled', style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
                if (h.message != null) ...[
                  const SizedBox(height: 8),
                  Text(h.message!,
                      maxLines: 2, overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: levelColor(h.level), fontSize: 12)),
                ],
                if (chips.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Wrap(spacing: 6, runSpacing: 6, children: chips),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _metricChip(String key, dynamic value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: const Color(0xFF8B949E).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text('${_metricLabel(key)} ${formatMetric(key, value)}',
          style: const TextStyle(fontSize: 11)),
    );
  }
}

String _metricLabel(String key) => key
    .replaceAll('_bytes_per_s', '/s')
    .replaceAll('_bytes', '')
    .replaceAll('_pct', '')
    .replaceAll('_', ' ');

/// Format a metric value for display, inferring units from the key suffix.
String formatMetric(String key, dynamic value) {
  if (value is! num) return '$value';
  if (key.endsWith('_bytes_per_s')) return '${humanBytes(value)}/s';
  if (key.endsWith('_bytes')) return humanBytes(value);
  if (key.endsWith('_pct')) return '${value.toStringAsFixed(1)}%';
  if (key.endsWith('_ms')) return '${value.toStringAsFixed(0)} ms';
  if (key.endsWith('_s')) return '${value.toStringAsFixed(0)}s';
  return value is int || value == value.roundToDouble()
      ? value.toInt().toString()
      : value.toStringAsFixed(1);
}

/// Humanize a byte count (1024-based, 1 decimal).
String humanBytes(num bytes) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  var v = bytes.toDouble();
  var i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return '${v.toStringAsFixed(i == 0 ? 0 : 1)} ${units[i]}';
}
