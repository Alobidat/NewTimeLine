/// Landing dashboard: headline counts, component health at a glance, recent activity.
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/health.dart';
import '../widgets/polling.dart';
import 'runs_screen.dart' show RunTile;

class OverviewScreen extends StatelessWidget {
  const OverviewScreen({super.key, required this.client, required this.onOpenComponent});

  final AdminClient client;
  final void Function(String componentId) onOpenComponent;

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<OverviewView>(
      interval: AdminConfig.pollInterval,
      fetch: client.overview,
      builder: (context, data) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('System', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: data.counts.entries
                .map((e) => _CountCard(label: e.key, value: e.value))
                .toList(),
          ),
          const SizedBox(height: 24),
          Text('Components', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: data.components
                .map((c) => _ComponentHealthCard(c: c, onTap: () => onOpenComponent(c.id)))
                .toList(),
          ),
          const SizedBox(height: 24),
          Text('Recent activity', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          if (data.recentRuns.isEmpty)
            const Padding(padding: EdgeInsets.all(8), child: Text('No runs yet.'))
          else
            ...data.recentRuns.map((r) => RunTile(run: r)),
        ],
      ),
    );
  }
}

class _CountCard extends StatelessWidget {
  const _CountCard({required this.label, required this.value});
  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Container(
        width: 150,
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('$value', style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 4),
            Text(label, style: Theme.of(context).textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}

class _ComponentHealthCard extends StatelessWidget {
  const _ComponentHealthCard({required this.c, required this.onTap});
  final ComponentView c;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 240,
      child: Card(
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(c.title,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                          overflow: TextOverflow.ellipsis),
                    ),
                    StatusChip(status: c.health.status),
                  ],
                ),
                const SizedBox(height: 6),
                Text(c.kind, style: Theme.of(context).textTheme.labelSmall),
                if (c.enabled == false)
                  const Padding(
                    padding: EdgeInsets.only(top: 6),
                    child: Text('disabled', style: TextStyle(color: Color(0xFFD29922))),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
