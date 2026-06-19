/// One component in depth: health, capabilities, actions, its config, and recent runs.
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/config_tile.dart';
import '../widgets/health.dart';
import '../widgets/polling.dart';
import 'runs_screen.dart' show RunTile;

class ComponentDetailScreen extends StatefulWidget {
  const ComponentDetailScreen({super.key, required this.client, required this.componentId});

  final AdminClient client;
  final String componentId;

  @override
  State<ComponentDetailScreen> createState() => _ComponentDetailScreenState();
}

class _ComponentDetailScreenState extends State<ComponentDetailScreen> {
  // Bumping this key forces the PollingBuilder to rebuild + refetch after an edit.
  int _reload = 0;

  Future<void> _action(String action) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.client.action(widget.componentId, action);
      messenger.showSnackBar(SnackBar(content: Text('$action ok')));
      setState(() => _reload++);
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Failed: $msg')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.componentId)),
      body: PollingBuilder<ComponentDetail>(
        key: ValueKey(_reload),
        interval: AdminConfig.pollInterval,
        fetch: () => widget.client.component(widget.componentId),
        builder: (context, c) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                Expanded(child: Text(c.title, style: Theme.of(context).textTheme.headlineSmall)),
                StatusChip(status: c.health.status),
              ],
            ),
            const SizedBox(height: 8),
            Text(c.description),
            const SizedBox(height: 12),
            _healthLine(context, c.health),
            if (c.capabilities.isNotEmpty) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: c.capabilities.map((cap) => Chip(label: Text(cap))).toList(),
              ),
            ],
            if (c.actions.isNotEmpty) ...[
              const SizedBox(height: 12),
              Wrap(spacing: 8, children: c.actions.map(_actionButton).toList()),
            ],
            if (c.config.isNotEmpty) ...[
              const Divider(height: 32),
              Text('Configuration', style: Theme.of(context).textTheme.titleMedium),
              ...c.config.map((e) => ConfigTile(
                    entry: e,
                    client: widget.client,
                    onChanged: () => setState(() => _reload++),
                  )),
            ],
            const Divider(height: 32),
            Text('Recent runs', style: Theme.of(context).textTheme.titleMedium),
            if (c.recentRuns.isEmpty)
              const Padding(padding: EdgeInsets.all(8), child: Text('No runs yet.'))
            else
              ...c.recentRuns.map((r) => RunTile(run: r)),
          ],
        ),
      ),
    );
  }

  Widget _actionButton(String action) {
    final enable = action == 'enable';
    final disable = action == 'disable';
    return FilledButton.tonalIcon(
      onPressed: () => _action(action),
      icon: Icon(enable
          ? Icons.play_arrow
          : disable
              ? Icons.pause
              : Icons.bolt),
      label: Text(action),
    );
  }

  Widget _healthLine(BuildContext context, HealthView h) {
    final parts = <String>[
      'runs: ${h.runs}',
      if (h.successRate != null) 'success: ${(h.successRate! * 100).round()}%',
      if (h.lastRunAt != null) 'last: ${h.lastRunAt!.toIso8601String()}',
    ];
    return Text(parts.join('   ·   '), style: Theme.of(context).textTheme.bodySmall);
  }
}
