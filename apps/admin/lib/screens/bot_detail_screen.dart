/// One AI user — persona, behaviour toggles, run-now, and recent posts/comments.
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../widgets/polling.dart';

class BotDetailScreen extends StatefulWidget {
  const BotDetailScreen({super.key, required this.client, required this.botId});
  final AdminClient client;
  final String botId;

  @override
  State<BotDetailScreen> createState() => _BotDetailScreenState();
}

class _BotDetailScreenState extends State<BotDetailScreen> {
  int _reload = 0;

  void _refresh() => setState(() => _reload++);

  Future<void> _patch(Map<String, dynamic> patch) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.client.updateBot(widget.botId, patch);
      _refresh();
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Failed: $msg')));
    }
  }

  Future<void> _action(String action) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.client.botAction(widget.botId, action);
      messenger.showSnackBar(SnackBar(content: Text('Enqueued $action job')));
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Failed: $msg')));
    }
  }

  Future<void> _retract(String eventId) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.client.retractPost(eventId);
      messenger.showSnackBar(const SnackBar(content: Text('Post retracted')));
      _refresh();
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Failed: $msg')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AI User')),
      body: PollingBuilder<BotDetail>(
        key: ValueKey(_reload),
        interval: const Duration(seconds: 10),
        fetch: () => widget.client.bot(widget.botId),
        builder: (context, b) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _header(context, b),
            const SizedBox(height: 16),
            _toggles(b),
            const SizedBox(height: 8),
            _runNow(),
            const SizedBox(height: 16),
            _stats(context, b),
            const SizedBox(height: 16),
            _section(context, 'Recent posts'),
            if (b.recentPosts.isEmpty) const ListTile(title: Text('— none yet')),
            ...b.recentPosts.map((p) => Card(
                  child: ListTile(
                    title: Text(p.title),
                    subtitle: Text('${p.category ?? ''} · ${p.status}'),
                    trailing: p.status == 'published'
                        ? TextButton(
                            onPressed: () => _retract(p.eventId),
                            child: const Text('Retract'),
                          )
                        : null,
                  ),
                )),
            const SizedBox(height: 16),
            _section(context, 'Recent comments'),
            if (b.recentComments.isEmpty) const ListTile(title: Text('— none yet')),
            ...b.recentComments.map((c) => Card(
                  child: ListTile(title: Text(c.body), dense: true),
                )),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext context, BotDetail b) {
    final avatar = b.avatarUrl;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CircleAvatar(
          radius: 32,
          backgroundImage: (avatar != null && avatar.isNotEmpty) ? NetworkImage(avatar) : null,
          child: (avatar == null || avatar.isEmpty)
              ? Text(b.label.isNotEmpty ? b.label[0].toUpperCase() : '?')
              : null,
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(b.label, style: Theme.of(context).textTheme.titleLarge),
              Text('@${b.handle} · ${b.tone ?? ''}'),
              const SizedBox(height: 4),
              Wrap(
                spacing: 6,
                children: b.interests
                    .map((i) => Chip(
                          label: Text(i),
                          visualDensity: VisualDensity.compact,
                          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ))
                    .toList(),
              ),
              if (b.persona != null) ...[
                const SizedBox(height: 8),
                Text(b.persona!, style: Theme.of(context).textTheme.bodyMedium),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _toggles(BotDetail b) => Card(
        child: Column(
          children: [
            SwitchListTile(
              title: const Text('Active (not suspended)'),
              value: b.enabled,
              onChanged: (v) => _patch({'enabled': v}),
            ),
            SwitchListTile(
              title: const Text('Posting enabled'),
              value: b.postsEnabled,
              onChanged: (v) => _patch({'posts_enabled': v}),
            ),
            SwitchListTile(
              title: const Text('Interaction enabled'),
              value: b.interactsEnabled,
              onChanged: (v) => _patch({'interacts_enabled': v}),
            ),
          ],
        ),
      );

  Widget _runNow() => Row(
        children: [
          Expanded(
            child: FilledButton.tonalIcon(
              icon: const Icon(Icons.video_call),
              label: const Text('Post now'),
              onPressed: () => _action('post'),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: FilledButton.tonalIcon(
              icon: const Icon(Icons.favorite),
              label: const Text('Interact now'),
              onPressed: () => _action('interact'),
            ),
          ),
        ],
      );

  Widget _stats(BuildContext context, BotDetail b) => Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Wrap(
            spacing: 24,
            runSpacing: 8,
            children: [
              _stat(context, '${b.postsCount}', 'posts'),
              _stat(context, '${b.interactionsCount}', 'interactions'),
              _stat(context, '${b.followers}', 'followers'),
              _stat(context, '${b.following}', 'following'),
              _stat(context, '${b.postCadenceMin}m', 'post cadence'),
              _stat(context, '${b.dailyPostCap}', 'daily post cap'),
              _stat(context, '${b.qualityThreshold}', 'quality floor'),
            ],
          ),
        ),
      );

  Widget _stat(BuildContext context, String value, String label) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: Theme.of(context).textTheme.titleMedium),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ],
      );

  Widget _section(BuildContext context, String title) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Text(title, style: Theme.of(context).textTheme.titleMedium),
      );
}
