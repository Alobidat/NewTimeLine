/// The top search bar on the Experience screen. Free-text search over events/places/people;
/// picking a result asks the parent to focus that event (zoom the map + morph the panel)
/// rather than pushing a separate route — search stays part of the one fluid surface.
library;

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
      suggestionsBuilder: (context, controller) async {
        final q = controller.text.trim();
        if (q.isEmpty) return const <Widget>[];
        List<EventRead> results;
        try {
          results = await api.search(q: q, limit: 20);
        } catch (_) {
          return const <Widget>[
            ListTile(
              leading: Icon(Icons.error_outline),
              title: Text('Search failed — is the API reachable?'),
            ),
          ];
        }
        if (results.isEmpty) {
          return const <Widget>[
            ListTile(leading: Icon(Icons.search_off), title: Text('No matches')),
          ];
        }
        return results.map(
          (e) => ListTile(
            leading: CircleAvatar(
              radius: 6,
              backgroundColor: severityColor(e.severity),
            ),
            title: Text(e.title, maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text(
              [
                formatLabel(e.tStart, e.precision, instant: e.instant),
                ?e.geoLabel,
              ].join('  ·  '),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            onTap: () {
              controller.closeView(e.title);
              onSelect(e);
            },
          ),
        );
      },
    );
  }
}
