/// Shared event-list widgets used by search, entity views, and the dig screen.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import '../event/event_detail_sheet.dart';
import '../theme/severity.dart';

/// A single event row → opens the detail sheet on tap.
class EventTile extends StatelessWidget {
  const EventTile({super.key, required this.api, required this.event, this.trailing});
  final ApiClient api;
  final EventRead event;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: CircleAvatar(
        radius: 6,
        backgroundColor: severityColor(event.severity),
      ),
      title: Text(event.title, maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        [
          formatLabel(event.tStart, event.precision, instant: event.instant),
          ?event.geoLabel,
        ].join('  ·  '),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: trailing,
      onTap: () => showEventDetail(context, api, event.id),
    );
  }
}

/// A scrollable list of events with an empty-state.
class EventList extends StatelessWidget {
  const EventList({super.key, required this.api, required this.events, this.empty});
  final ApiClient api;
  final List<EventRead> events;
  final String? empty;

  @override
  Widget build(BuildContext context) {
    if (events.isEmpty) {
      return Center(child: Text(empty ?? 'No events.'));
    }
    return ListView.separated(
      itemCount: events.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (_, i) => EventTile(api: api, event: events[i]),
    );
  }
}

/// A screen that resolves a future of events and lists them (entity events, the
/// US↔Iran arc, etc.).
class ResultsScreen extends StatelessWidget {
  const ResultsScreen({super.key, required this.api, required this.title, required this.future});
  final ApiClient api;
  final String title;
  final Future<List<EventRead>> future;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: FutureBuilder<List<EventRead>>(
        future: future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('Failed: ${snap.error}'));
          }
          return EventList(api: api, events: snap.data!, empty: 'Nothing found.');
        },
      ),
    );
  }
}
