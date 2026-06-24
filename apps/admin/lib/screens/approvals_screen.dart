/// Moderation approvals queue: open flags raised by the LLM pass, with Approve (clear + un-hold)
/// and Remove (retract content) actions. Polls so it stays fresh.
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/polling.dart';

class ApprovalsScreen extends StatefulWidget {
  const ApprovalsScreen({super.key, required this.client});
  final AdminClient client;

  @override
  State<ApprovalsScreen> createState() => _ApprovalsScreenState();
}

class _ApprovalsScreenState extends State<ApprovalsScreen> {
  int _refresh = 0;
  String? _busyId;

  Future<void> _act(String id, Future<void> Function() action) async {
    setState(() => _busyId = id);
    try {
      await action();
      if (mounted) setState(() => _refresh++); // force a re-fetch
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
      }
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<ModerationQueue>(
      key: ValueKey(_refresh),
      interval: AdminConfig.pollInterval,
      fetch: () => widget.client.moderationQueue(),
      builder: (context, queue) {
        if (queue.items.isEmpty) {
          return const Center(child: Text('No open flags — the queue is clear.'));
        }
        return ListView(
          padding: const EdgeInsets.all(12),
          children: [
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text('${queue.count} open flag${queue.count == 1 ? '' : 's'}',
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            for (final f in queue.items) _FlagCard(
              flag: f,
              busy: _busyId == f.id,
              onApprove: () => _act(f.id, () => widget.client.approveFlag(f.id)),
              onRemove: () => _act(f.id, () => widget.client.removeFlag(f.id)),
            ),
          ],
        );
      },
    );
  }
}

class _FlagCard extends StatelessWidget {
  const _FlagCard({
    required this.flag,
    required this.busy,
    required this.onApprove,
    required this.onRemove,
  });
  final ModerationFlag flag;
  final bool busy;
  final VoidCallback onApprove;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final sevColor = flag.severity >= 90
        ? Colors.red
        : flag.severity >= 60
            ? Colors.orange
            : Colors.amber;
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Chip(
                  label: Text(flag.targetType),
                  visualDensity: VisualDensity.compact,
                ),
                const SizedBox(width: 8),
                CircleAvatar(radius: 12, backgroundColor: sevColor,
                    child: Text('${flag.severity}',
                        style: const TextStyle(fontSize: 10, color: Colors.white))),
                const SizedBox(width: 8),
                Text('via ${flag.source}', style: Theme.of(context).textTheme.bodySmall),
                if (flag.held) ...[
                  const SizedBox(width: 8),
                  const Chip(
                    label: Text('held'),
                    visualDensity: VisualDensity.compact,
                    backgroundColor: Color(0x33FF0000),
                  ),
                ],
              ],
            ),
            if (flag.reason != null && flag.reason!.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(flag.reason!, style: const TextStyle(fontStyle: FontStyle.italic)),
            ],
            if (flag.preview != null) ...[
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(flag.preview!),
              ),
            ],
            const SizedBox(height: 10),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (busy)
                  const Padding(
                    padding: EdgeInsets.only(right: 12),
                    child: SizedBox(
                        width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                  ),
                TextButton.icon(
                  onPressed: busy ? null : onApprove,
                  icon: const Icon(Icons.check_circle_outline, color: Colors.green),
                  label: const Text('Approve'),
                ),
                const SizedBox(width: 8),
                FilledButton.icon(
                  onPressed: busy ? null : onRemove,
                  style: FilledButton.styleFrom(backgroundColor: Colors.red),
                  icon: const Icon(Icons.delete_outline),
                  label: const Text('Remove'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
