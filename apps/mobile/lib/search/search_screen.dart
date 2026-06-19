/// Search entry point: find events by title or a linked entity name, then tap to open
/// detail and dig. Also offers quick entity shortcuts (e.g. the US ↔ Iran relationship).
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import 'results_list.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.api});
  final ApiClient api;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _controller = TextEditingController();
  Future<List<EventRead>>? _results;
  String _query = '';

  void _run(String q) {
    q = q.trim();
    if (q.isEmpty) return;
    setState(() {
      _query = q;
      _results = widget.api.search(q: q, limit: 100);
    });
  }

  /// Find two entities by name and show the events linking BOTH (the signature query).
  Future<void> _relationship(String a, String b) async {
    setState(() {
      _query = '$a ↔ $b';
      _results = () async {
        final ea = await widget.api.entities(q: a, limit: 5);
        final eb = await widget.api.entities(q: b, limit: 5);
        if (ea.isEmpty || eb.isEmpty) return <EventRead>[];
        return widget.api.eventsByEntities([ea.first.id, eb.first.id], limit: 200);
      }();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _controller,
          autofocus: true,
          textInputAction: TextInputAction.search,
          decoration: const InputDecoration(
            hintText: 'Search events, people, places…',
            border: InputBorder.none,
          ),
          onSubmitted: _run,
        ),
        actions: [
          IconButton(icon: const Icon(Icons.search), onPressed: () => _run(_controller.text)),
        ],
      ),
      body: _results == null
          ? _Suggestions(onRelationship: _relationship, onTerm: (t) {
              _controller.text = t;
              _run(t);
            })
          : Column(
              children: [
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text('Results for "$_query"',
                        style: Theme.of(context).textTheme.labelLarge),
                  ),
                ),
                Expanded(
                  child: FutureBuilder<List<EventRead>>(
                    future: _results,
                    builder: (context, snap) {
                      if (snap.connectionState != ConnectionState.done) {
                        return const Center(child: CircularProgressIndicator());
                      }
                      if (snap.hasError) {
                        return Center(child: Text('Failed: ${snap.error}'));
                      }
                      return EventList(
                        api: widget.api,
                        events: snap.data!,
                        empty: 'Nothing found for "$_query".',
                      );
                    },
                  ),
                ),
              ],
            ),
    );
  }
}

class _Suggestions extends StatelessWidget {
  const _Suggestions({required this.onRelationship, required this.onTerm});
  final void Function(String a, String b) onRelationship;
  final void Function(String term) onTerm;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Try a relationship', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: [
            ActionChip(
              avatar: const Icon(Icons.account_tree_outlined, size: 16),
              label: const Text('US ↔ Iran'),
              onPressed: () => onRelationship('United States', 'Iran'),
            ),
          ],
        ),
        const SizedBox(height: 20),
        Text('Or search a term', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: ['Iran', 'Soleimani', 'nuclear', 'revolution']
              .map((t) => ActionChip(label: Text(t), onPressed: () => onTerm(t)))
              .toList(),
        ),
      ],
    );
  }
}
