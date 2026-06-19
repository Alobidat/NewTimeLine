/// Component list — every managed agent/service/store with health + enable toggle.
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/health.dart';
import '../widgets/polling.dart';
import 'component_detail_screen.dart';

class ComponentsScreen extends StatelessWidget {
  const ComponentsScreen({super.key, required this.client});
  final AdminClient client;

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<List<ComponentView>>(
      interval: AdminConfig.pollInterval,
      fetch: () => client.components(),
      builder: (context, items) => ListView(
        padding: const EdgeInsets.all(8),
        children: items.map((c) => _ComponentRow(c: c, client: client)).toList(),
      ),
    );
  }
}

class _ComponentRow extends StatelessWidget {
  const _ComponentRow({required this.c, required this.client});
  final ComponentView c;
  final AdminClient client;

  Future<void> _toggle(BuildContext context, bool enable) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await client.action(c.id, enable ? 'enable' : 'disable');
      messenger.showSnackBar(SnackBar(content: Text('${enable ? 'Enabled' : 'Disabled'} ${c.title}')));
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Failed: $msg')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(statusIcon(c.health.status), color: statusColor(c.health.status)),
        title: Text(c.title),
        subtitle: Text('${c.id}\n${c.description}'),
        isThreeLine: true,
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            StatusChip(status: c.health.status),
            if (c.enabled != null) ...[
              const SizedBox(width: 8),
              Switch(value: c.enabled!, onChanged: (v) => _toggle(context, v)),
            ],
          ],
        ),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => ComponentDetailScreen(client: client, componentId: c.id)),
        ),
      ),
    );
  }
}
