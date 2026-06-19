/// Coarse system status (resource dashboards expand this later).
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/health.dart';
import '../widgets/polling.dart';

class SystemScreen extends StatelessWidget {
  const SystemScreen({super.key, required this.client});
  final AdminClient client;

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<SystemView>(
      interval: AdminConfig.pollInterval,
      fetch: client.system,
      builder: (context, s) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _row('Environment', s.environment),
          _row('Database', s.database, status: s.database == 'ok' ? 'ok' : 'error'),
          _row('Config keys', '${s.configKeys}'),
          _row('Components', '${s.components}'),
          _row('Running agents', '${s.runningAgents}',
              status: s.runningAgents > 0 ? 'running' : null),
          const SizedBox(height: 16),
          const Card(
            child: ListTile(
              leading: Icon(Icons.info_outline),
              title: Text('Resource metrics (CPU/memory/queue depth) arrive with the '
                  'observability stack; this view is the coarse status for now.'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _row(String label, String value, {String? status}) => Card(
        child: ListTile(
          title: Text(label),
          trailing: status == null
              ? Text(value, style: const TextStyle(fontWeight: FontWeight.w600))
              : StatusChip(status: status),
        ),
      );
}
