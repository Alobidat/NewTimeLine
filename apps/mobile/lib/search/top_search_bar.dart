/// The top search bar on the Experience screen. Faceted free-text search over
/// events / actors / places (event-presentation.md §5.1, ADR-0022); picking an event asks
/// the parent to focus it (zoom the map + morph the panel) rather than pushing a route —
/// search stays part of the one fluid surface.
///
/// Search also triggers live collection: the backend enqueues an on-demand `collect` job
/// and we subscribe to `/search/stream`, so the panel shows "showing N results, collecting
/// more…" and refreshes as freshly-collected events land.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import '../theme/severity.dart';

class TopSearchBar extends StatelessWidget {
  const TopSearchBar({super.key, required this.api, required this.onSelect});

  final ApiClient api;
  final void Function(EventRead event) onSelect;

  @override
  Widget build(BuildContext context) {
    return SearchAnchor.bar(
      barHintText: 'Search events, places, people…',
      barLeading: const Icon(Icons.search),
      isFullScreen: false,
      suggestionsBuilder: (context, controller) {
        final q = controller.text.trim();
        if (q.isEmpty) return const <Widget>[];
        // One live widget owns the faceted query + the SSE refresh. Returned as a single
        // suggestion so it persists (and keeps streaming) across rebuilds for this query.
        return <Widget>[
          _LiveSearchResults(
            key: ValueKey(q),
            api: api,
            query: q,
            onSelect: (e) {
              controller.closeView(e.title);
              onSelect(e);
            },
          ),
        ];
      },
    );
  }
}

/// Runs the faceted search for [query], renders events / actors / places, and subscribes
/// to the live-collection stream — appending newly-collected events and updating the
/// "collecting more…" indicator as they arrive.
class _LiveSearchResults extends StatefulWidget {
  const _LiveSearchResults({
    super.key,
    required this.api,
    required this.query,
    required this.onSelect,
  });

  final ApiClient api;
  final String query;
  final void Function(EventRead event) onSelect;

  @override
  State<_LiveSearchResults> createState() => _LiveSearchResultsState();
}

class _LiveSearchResultsState extends State<_LiveSearchResults> {
  SearchResults? _results;
  Object? _error;
  bool _collecting = false;
  final List<EventRead> _events = [];
  final Set<String> _seen = {};
  StreamSubscription<EventRead>? _sub;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    try {
      final res = await widget.api.search(q: widget.query, limit: 20);
      if (!mounted) return;
      setState(() {
        _results = res;
        _collecting = res.collecting;
        for (final e in res.events) {
          if (_seen.add(e.id)) _events.add(e);
        }
      });
      if (res.collecting) _subscribe();
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  void _subscribe() {
    _sub = widget.api.searchStream(q: widget.query, limit: 20).listen(
      (e) {
        if (!mounted) return;
        if (_seen.add(e.id)) {
          // Newly-collected events land first (they're the fresh ones).
          setState(() => _events.insert(0, e));
        }
      },
      onDone: () {
        if (mounted) setState(() => _collecting = false);
      },
      onError: (_) {
        if (mounted) setState(() => _collecting = false);
      },
    );
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return const ListTile(
        leading: Icon(Icons.error_outline),
        title: Text('Search failed — is the API reachable?'),
      );
    }
    final res = _results;
    if (res == null) {
      return const Padding(
        padding: EdgeInsets.all(24),
        child: Center(child: CircularProgressIndicator()),
      );
    }

    final children = <Widget>[];

    if (_collecting) {
      children.add(_CollectingBanner(count: _events.length));
    }

    if (res.places.isNotEmpty) {
      children.add(const _FacetHeader('Places'));
      children.addAll(res.places.map(_entityTile));
    }
    if (res.actors.isNotEmpty) {
      children.add(const _FacetHeader('People & organisations'));
      children.addAll(res.actors.map(_entityTile));
    }

    children.add(const _FacetHeader('Events'));
    if (_events.isEmpty) {
      children.add(
        ListTile(
          leading: const Icon(Icons.search_off),
          title: Text(_collecting ? 'No matches yet…' : 'No matches'),
        ),
      );
    } else {
      children.addAll(_events.map(_eventTile));
    }

    return Column(mainAxisSize: MainAxisSize.min, children: children);
  }

  Widget _eventTile(EventRead e) => ListTile(
    leading: CircleAvatar(radius: 6, backgroundColor: severityColor(e.severity)),
    title: Text(e.title, maxLines: 1, overflow: TextOverflow.ellipsis),
    subtitle: Text(
      [
        formatLabel(e.tStart, e.precision, instant: e.instant),
        ?e.geoLabel,
      ].join('  ·  '),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
    ),
    onTap: () => widget.onSelect(e),
  );

  Widget _entityTile(EntityRead en) => ListTile(
    dense: true,
    leading: Icon(en.kind == 'place' ? Icons.place_outlined : Icons.person_outline, size: 18),
    title: Text(en.name, maxLines: 1, overflow: TextOverflow.ellipsis),
    trailing: en.eventCount == null ? null : Text('${en.eventCount}'),
  );
}

class _FacetHeader extends StatelessWidget {
  const _FacetHeader(this.label);
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Text(
        label.toUpperCase(),
        style: Theme.of(context).textTheme.labelSmall?.copyWith(letterSpacing: 0.8),
      ),
    );
  }
}

/// "Showing N results, collecting more…" — the live-collection indicator.
class _CollectingBanner extends StatelessWidget {
  const _CollectingBanner({required this.count});
  final int count;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Row(
        children: [
          const SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Showing $count result${count == 1 ? '' : 's'}, collecting more…',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}
