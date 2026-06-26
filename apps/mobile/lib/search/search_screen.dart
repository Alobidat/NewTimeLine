/// Search entry point: find events, **creators** (authors/bots), people and places by keyword,
/// then tap to open detail and dig. A "Videos only" toggle restricts to clip results. Also
/// offers quick entity shortcuts (e.g. the US ↔ Iran relationship).
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../profile/avatar.dart';
import '../profile/user_profile_page.dart';
import '../state/auth_state.dart';
import 'results_list.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.api, this.auth});
  final ApiClient api;
  final AuthState? auth;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _controller = TextEditingController();
  // Own a transient auth only if the caller didn't supply one (so a profile still opens).
  late final AuthState _auth = widget.auth ?? AuthState(api: widget.api);
  late final bool _ownsAuth = widget.auth == null;
  Future<SearchResults>? _results;
  String _query = '';
  bool _videosOnly = false;

  void _run(String q) {
    q = q.trim();
    if (q.isEmpty) return;
    setState(() {
      _query = q;
      // Faceted search (events + creators + people/places) also triggers live collection.
      _results = widget.api.search(
        q: q,
        media: _videosOnly ? 'video' : null,
        limit: 100,
      );
    });
  }

  /// Find two entities by name and show the events linking BOTH (the signature query).
  Future<void> _relationship(String a, String b) async {
    setState(() {
      _query = '$a ↔ $b';
      _results = () async {
        final ea = await widget.api.entities(q: a, limit: 5);
        final eb = await widget.api.entities(q: b, limit: 5);
        final events = (ea.isEmpty || eb.isEmpty)
            ? <EventRead>[]
            : await widget.api.eventsByEntities([ea.first.id, eb.first.id], limit: 200);
        return SearchResults(subject: '$a ↔ $b', events: events);
      }();
    });
  }

  void _openProfile(UserSummary u) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => UserProfilePage(api: widget.api, auth: _auth, userId: u.id),
    ));
  }

  @override
  void dispose() {
    _controller.dispose();
    if (_ownsAuth) _auth.dispose();
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
            hintText: 'Search events, authors, people, places…',
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
                Row(
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
                      child: Text('Results for "$_query"',
                          style: Theme.of(context).textTheme.labelLarge),
                    ),
                    const Spacer(),
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        key: const Key('search-videos-only'),
                        label: const Text('Videos only'),
                        selected: _videosOnly,
                        onSelected: (v) {
                          setState(() => _videosOnly = v);
                          _run(_query);
                        },
                      ),
                    ),
                  ],
                ),
                Expanded(
                  child: FutureBuilder<SearchResults>(
                    future: _results,
                    builder: (context, snap) {
                      if (snap.connectionState != ConnectionState.done) {
                        return const Center(child: CircularProgressIndicator());
                      }
                      if (snap.hasError) {
                        return Center(child: Text('Failed: ${snap.error}'));
                      }
                      final r = snap.data!;
                      if (r.isEmpty) {
                        return Center(child: Text('Nothing found for "$_query".'));
                      }
                      return ListView(
                        children: [
                          if (r.creators.isNotEmpty)
                            _CreatorsStrip(creators: r.creators, onTap: _openProfile),
                          for (final e in r.events) EventTile(api: widget.api, event: e),
                          if (r.events.isEmpty)
                            const Padding(
                              padding: EdgeInsets.all(24),
                              child: Center(child: Text('No matching events.')),
                            ),
                        ],
                      );
                    },
                  ),
                ),
              ],
            ),
    );
  }
}

/// Horizontal row of matching creators (authors/bots) — tap to open their profile.
class _CreatorsStrip extends StatelessWidget {
  const _CreatorsStrip({required this.creators, required this.onTap});
  final List<UserSummary> creators;
  final void Function(UserSummary) onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Text('Creators', style: Theme.of(context).textTheme.titleSmall),
        ),
        SizedBox(
          height: 96,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            itemCount: creators.length,
            separatorBuilder: (_, _) => const SizedBox(width: 4),
            itemBuilder: (_, i) {
              final c = creators[i];
              return InkWell(
                key: Key('creator-${c.handle}'),
                onTap: () => onTap(c),
                borderRadius: BorderRadius.circular(8),
                child: SizedBox(
                  width: 84,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const SizedBox(height: 8),
                      Avatar(label: c.label, url: c.avatarUrl, radius: 24),
                      const SizedBox(height: 6),
                      Text('@${c.handle}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        const Divider(height: 16),
      ],
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
