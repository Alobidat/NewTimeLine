/// Storage usage — media by status/disposition + stored bytes + headline totals.
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/polling.dart';

class StorageScreen extends StatelessWidget {
  const StorageScreen({super.key, required this.client});
  final AdminClient client;

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<StorageView>(
      interval: AdminConfig.pollInterval,
      fetch: client.storage,
      builder: (context, s) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              leading: const Icon(Icons.save, size: 32),
              title: Text(_humanBytes(s.mediaStoredBytes),
                  style: Theme.of(context).textTheme.headlineSmall),
              subtitle: const Text('media stored locally (object store)'),
            ),
          ),
          const SizedBox(height: 16),
          _Breakdown(title: 'Media by disposition', data: s.mediaByDisposition),
          const SizedBox(height: 16),
          _Breakdown(title: 'Media by status', data: s.mediaByStatus),
          const SizedBox(height: 16),
          _Breakdown(title: 'Totals', data: s.totals),
        ],
      ),
    );
  }
}

class _Breakdown extends StatelessWidget {
  const _Breakdown({required this.title, required this.data});
  final String title;
  final Map<String, int> data;

  @override
  Widget build(BuildContext context) {
    final total = data.values.fold<int>(0, (a, b) => a + b);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            if (data.isEmpty)
              const Text('—')
            else
              for (final e in data.entries) _Bar(label: e.key, value: e.value, total: total),
          ],
        ),
      ),
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar({required this.label, required this.value, required this.total});
  final String label;
  final int value;
  final int total;

  @override
  Widget build(BuildContext context) {
    final frac = total == 0 ? 0.0 : value / total;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(width: 120, child: Text(label)),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(value: frac, minHeight: 10),
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(width: 48, child: Text('$value', textAlign: TextAlign.end)),
        ],
      ),
    );
  }
}

String _humanBytes(int b) {
  if (b < 1024) return '$b B';
  const units = ['KB', 'MB', 'GB', 'TB'];
  double v = b / 1024;
  var i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return '${v.toStringAsFixed(1)} ${units[i]}';
}
