/// AI Users — the bot-persona roster with status, counts, and a bulk bootstrap.
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/polling.dart';
import 'bot_detail_screen.dart';

class BotsScreen extends StatelessWidget {
  const BotsScreen({super.key, required this.client});
  final AdminClient client;

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<BotRoster>(
      interval: AdminConfig.pollInterval,
      fetch: () => client.bots(),
      builder: (context, roster) => Column(
        children: [
          _Header(roster: roster, client: client),
          const Divider(height: 1),
          Expanded(
            child: roster.bots.isEmpty
                ? const Center(child: Text('No AI users yet — use Bootstrap to create some.'))
                : ListView(
                    padding: const EdgeInsets.all(8),
                    children:
                        roster.bots.map((b) => _BotRow(b: b, client: client)).toList(),
                  ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.roster, required this.client});
  final BotRoster roster;
  final AdminClient client;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      child: Row(
        children: [
          Text('${roster.total} AI users · ${roster.enabled} active',
              style: Theme.of(context).textTheme.titleMedium),
          const Spacer(),
          FilledButton.tonalIcon(
            icon: const Icon(Icons.auto_awesome),
            label: const Text('Bootstrap'),
            onPressed: () => _bootstrap(context),
          ),
        ],
      ),
    );
  }

  Future<void> _bootstrap(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    final count = await showDialog<int>(
      context: context,
      builder: (_) => const _BootstrapDialog(),
    );
    if (count == null) return;
    try {
      await client.bootstrapBots(count, 2);
      messenger.showSnackBar(
        SnackBar(content: Text('Bootstrap of $count AI users enqueued — they\'ll appear shortly.')),
      );
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Failed: $msg')));
    }
  }
}

class _BootstrapDialog extends StatefulWidget {
  const _BootstrapDialog();
  @override
  State<_BootstrapDialog> createState() => _BootstrapDialogState();
}

class _BootstrapDialogState extends State<_BootstrapDialog> {
  double _count = 50;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Bootstrap AI users'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Create ${_count.round()} personas (with avatars) and seed ~2 posts each.'),
          Slider(
            value: _count,
            min: 5,
            max: 300,
            divisions: 59,
            label: '${_count.round()}',
            onChanged: (v) => setState(() => _count = v),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () => Navigator.pop(context, _count.round()),
          child: const Text('Create'),
        ),
      ],
    );
  }
}

class _BotRow extends StatelessWidget {
  const _BotRow({required this.b, required this.client});
  final BotView b;
  final AdminClient client;

  @override
  Widget build(BuildContext context) {
    final avatar = b.avatarUrl;
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundImage: (avatar != null && avatar.isNotEmpty) ? NetworkImage(avatar) : null,
          child: (avatar == null || avatar.isEmpty)
              ? Text(b.label.isNotEmpty ? b.label[0].toUpperCase() : '?')
              : null,
        ),
        title: Row(
          children: [
            Flexible(child: Text(b.label, overflow: TextOverflow.ellipsis)),
            if (!b.enabled) ...[
              const SizedBox(width: 6),
              const Chip(
                label: Text('suspended'),
                visualDensity: VisualDensity.compact,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ],
          ],
        ),
        subtitle: Text(
          '@${b.handle} · ${b.interests.join(", ")}\n'
          '${b.postsCount} posts · ${b.interactionsCount} interactions',
        ),
        isThreeLine: true,
        trailing: Icon(
          b.enabled ? Icons.smart_toy : Icons.toggle_off,
          color: b.enabled ? Colors.green : Colors.grey,
        ),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => BotDetailScreen(client: client, botId: b.id)),
        ),
      ),
    );
  }
}
