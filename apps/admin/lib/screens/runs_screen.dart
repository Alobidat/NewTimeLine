/// Agent run history — what ran, when, with what result.
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/health.dart';
import '../widgets/polling.dart';

class RunsScreen extends StatelessWidget {
  const RunsScreen({super.key, required this.client, this.componentId});

  final AdminClient client;
  final String? componentId;

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<List<RunView>>(
      interval: AdminConfig.pollInterval,
      fetch: () => client.runs(component: componentId, limit: 100),
      builder: (context, runs) {
        if (runs.isEmpty) {
          return ListView(
            children: const [Padding(padding: EdgeInsets.all(24), child: Text('No runs recorded yet.'))],
          );
        }
        return ListView(
          padding: const EdgeInsets.all(8),
          children: runs.map((r) => RunTile(run: r)).toList(),
        );
      },
    );
  }
}

/// One run row — reused on the overview + component detail.
class RunTile extends StatelessWidget {
  const RunTile({super.key, required this.run});
  final RunView run;

  @override
  Widget build(BuildContext context) {
    final when = run.startedAt;
    final stamp = '${when.year}-${_two(when.month)}-${_two(when.day)} '
        '${_two(when.hour)}:${_two(when.minute)}';
    final stats = run.stats == null || run.stats!.isEmpty
        ? null
        : run.stats!.entries.map((e) => '${e.key}=${e.value}').join('  ');
    return ListTile(
      dense: true,
      leading: Icon(statusIcon(run.status), color: statusColor(run.status)),
      title: Text('${run.componentId}  ·  ${run.command}'),
      subtitle: Text([stamp, ?stats, ?run.error].join('\n')),
      isThreeLine: stats != null || run.error != null,
      trailing: StatusChip(status: run.status),
    );
  }

  static String _two(int n) => n.toString().padLeft(2, '0');
}
