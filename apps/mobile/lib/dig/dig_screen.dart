/// The "dig" view: from a root event, show what **led to it** (back) and what it
/// **caused** (forward) by walking the causal chain (/events/{id}/chain). Tapping any
/// event opens its detail, from which you can dig again — recursive history navigation.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import '../search/results_list.dart';

class DigScreen extends StatefulWidget {
  const DigScreen({super.key, required this.api, required this.root});
  final ApiClient api;
  final EventRead root;

  @override
  State<DigScreen> createState() => _DigScreenState();
}

class _DigScreenState extends State<DigScreen> {
  late Future<List<ChainResponse>> _chains;

  @override
  void initState() {
    super.initState();
    _chains = Future.wait([
      widget.api.chain(widget.root.id, direction: 'back', depth: 8),
      widget.api.chain(widget.root.id, direction: 'forward', depth: 8),
    ]);
  }

  /// Chain nodes minus the root, oldest first.
  List<EventRead> _nodes(ChainResponse c) =>
      (c.nodes.where((n) => n.id != widget.root.id).toList()
        ..sort((a, b) => a.tStart.compareTo(b.tStart)));

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Dig the history')),
      body: FutureBuilder<List<ChainResponse>>(
        future: _chains,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('Failed: ${snap.error}'));
          }
          final back = _nodes(snap.data![0]);
          final forward = _nodes(snap.data![1]);
          return ListView(
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                color: theme.colorScheme.surfaceContainerHighest,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(widget.root.title, style: theme.textTheme.titleMedium),
                    Text(
                      formatLabel(widget.root.tStart, widget.root.precision,
                          instant: widget.root.instant),
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              _ChainSection(
                api: widget.api,
                icon: Icons.south,
                title: 'What led to this  (${back.length})',
                events: back,
                empty: 'No earlier events linked yet.',
              ),
              _ChainSection(
                api: widget.api,
                icon: Icons.north,
                title: 'What this caused  (${forward.length})',
                events: forward,
                empty: 'No later events linked yet.',
              ),
            ],
          );
        },
      ),
    );
  }
}

class _ChainSection extends StatelessWidget {
  const _ChainSection({
    required this.api,
    required this.icon,
    required this.title,
    required this.events,
    required this.empty,
  });

  final ApiClient api;
  final IconData icon;
  final String title;
  final List<EventRead> events;
  final String empty;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: Row(
            children: [
              Icon(icon, size: 18),
              const SizedBox(width: 8),
              Text(title, style: Theme.of(context).textTheme.titleSmall),
            ],
          ),
        ),
        if (events.isEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Text(empty, style: Theme.of(context).textTheme.bodySmall),
          )
        else
          ...events.map((e) => EventTile(api: api, event: e)),
        const Divider(height: 1),
      ],
    );
  }
}
