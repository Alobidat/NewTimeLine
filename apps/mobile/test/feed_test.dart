// Tests for the TikTok-style feed shell (Phase 4-F, ADR-0027). Covers:
//   • FeedSource shimming the live endpoints into FeedItems,
//   • the vertical feed rendering a page with the full overlay rail,
//   • vertical paging (swipe up advances to the next event),
//   • the bottom Timeline-web button opening the graph/timeline web,
//   • the graph layout placing the root + related nodes.
// Network is faked with http's MockClient — no live API (the /feed endpoint isn't live yet).

import 'dart:convert';

import 'package:chronos_app/api/client.dart';
import 'package:chronos_app/api/models.dart';
import 'package:chronos_app/domain/time_format.dart';
import 'package:chronos_app/feed/event_graph_view.dart';
import 'package:chronos_app/feed/feed_source.dart';
import 'package:chronos_app/feed/overlay_rail.dart';
import 'package:chronos_app/feed/video_feed.dart';
import 'package:chronos_app/state/auth_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _eventJson(String id, String title, double t) => {
  'id': id,
  'title': title,
  't_start': t,
  't_end': t,
  'time_precision': 'year',
  'severity': 30,
  'confidence': 50,
  'source_count': 1,
};

EventRead _event(String id, String title, double t) =>
    EventRead.fromJson(_eventJson(id, title, t));

Map<String, dynamic> _relJson(
  Map<String, dynamic> event,
  String kind,
  String direction,
) => {
  'event': event,
  'kind': kind,
  'weight': 1.0,
  'direction': direction,
};

/// A MockClient serving the ranked `/feed/{tab}` and a fixed /related payload.
ApiClient _api({
  List<Map<String, dynamic>>? timelineEvents,
  List<Map<String, dynamic>>? related,
  String? feedNextCursor,
}) {
  final mock = MockClient((req) async {
    final path = req.url.path;
    if (path.startsWith('/feed/')) {
      final tab = path.substring('/feed/'.length);
      return http.Response(
        jsonEncode({
          'tab': tab,
          'items': [
            for (final e in timelineEvents ?? const [])
              {'event': e, 'hero_media_id': null, 'score': 1.0},
          ],
          'next_cursor': feedNextCursor,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (path.endsWith('/related')) {
      return http.Response(jsonEncode(related ?? const []), 200,
          headers: {'content-type': 'application/json'});
    }
    // Reactions / comments / everything else: empty-ish 200 so widgets don't error.
    if (path.endsWith('/reactions')) {
      return http.Response(
          jsonEncode({'event_id': 'x', 'counts': {}, 'mine': []}), 200,
          headers: {'content-type': 'application/json'});
    }
    return http.Response('[]', 200,
        headers: {'content-type': 'application/json'});
  });
  return ApiClient(baseUrl: 'http://test', client: mock);
}

void main() {
  group('FeedSource', () {
    test('maps a /feed page into video-first FeedItems', () async {
      final api = _api(timelineEvents: [
        _eventJson('e1', 'First', 2001),
        _eventJson('e2', 'Second', 2002),
      ]);
      addTearDown(api.close);
      final page = await FeedSource(api).page(FeedTab.forYou);
      expect(page.items.length, 2);
      expect(page.items.first.event.id, 'e1');
      expect(page.nextCursor, isNull); // last page → no cursor
    });

    test('threads the opaque next_cursor through for paging', () async {
      final api = _api(
        timelineEvents: [_eventJson('e1', 'First', 2001)],
        feedNextCursor: 'cursor-2',
      );
      addTearDown(api.close);
      final page = await FeedSource(api).page(FeedTab.discover);
      expect(page.items.single.event.id, 'e1');
      expect(page.nextCursor, 'cursor-2');
    });

    test('each tab maps to its future /feed slug', () {
      expect(FeedTab.forYou.slug, 'foryou');
      expect(FeedTab.following.slug, 'following');
      expect(FeedTab.discover.slug, 'discover');
    });
  });

  group('VideoFeed', () {
    Future<void> pumpFeed(WidgetTester tester, ApiClient api) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: VideoFeed(
              api: api,
              auth: AuthState(api: api),
              source: FeedSource(api),
              tab: FeedTab.forYou,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('renders a page with the full overlay rail', (tester) async {
      final api = _api(timelineEvents: [
        _eventJson('e1', 'Berlin Wall falls', 1989),
        _eventJson('e2', 'Reunification', 1990),
      ]);
      addTearDown(api.close);
      await pumpFeed(tester, api);

      // The active page's caption + every rail button are present.
      expect(find.text('Berlin Wall falls'), findsOneWidget);
      expect(find.byKey(const Key('rail-react')), findsOneWidget);
      expect(find.byKey(const Key('rail-comment')), findsOneWidget);
      expect(find.byKey(const Key('rail-promote-up')), findsOneWidget);
      expect(find.byKey(const Key('rail-promote-down')), findsOneWidget);
      expect(find.byKey(const Key('rail-follow')), findsOneWidget);
      expect(find.byKey(const Key('rail-share')), findsOneWidget);
      expect(find.byKey(const Key('rail-info')), findsOneWidget);
    });

    testWidgets('swipe up pages to the next event video', (tester) async {
      final api = _api(timelineEvents: [
        _eventJson('e1', 'Berlin Wall falls', 1989),
        _eventJson('e2', 'Reunification', 1990),
      ]);
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.text('Berlin Wall falls'), findsOneWidget);
      // Drag up → the feed's gesture surface advances to the next clip.
      await tester.fling(
          find.byKey(const Key('feed-gestures')), const Offset(0, -600), 1000);
      await tester.pumpAndSettle();
      expect(find.text('Reunification'), findsOneWidget);
    });

    testWidgets('the bottom Timeline-web button opens the graph', (tester) async {
      final api = _api(
        timelineEvents: [_eventJson('e1', 'Root', 2000)],
        related: [
          _relJson(_eventJson('e2', 'Caused this', 2001), 'caused', 'forward'),
        ],
      );
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.text('Root'), findsOneWidget);
      // The graph/timeline web is now a bottom button (it used to be swipe-right; that gesture
      // now walks the timeline forward instead).
      await tester.tap(find.byKey(const Key('feed-graph')));
      await tester.pumpAndSettle();

      expect(find.byType(EventGraphView), findsOneWidget);
      expect(find.text('History web'), findsOneWidget);
    });
  });

  group('GraphTimeline', () {
    testWidgets('places the root and its related nodes', (tester) async {
      final opened = <String>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: GraphTimeline(
              root: _event('e1', 'Root event', 2000),
              related: [
                RelatedEvent(
                  event: _event('e2', 'Earlier', 1999),
                  kind: 'precursor',
                  weight: 1,
                  direction: 'back',
                ),
                RelatedEvent(
                  event: _event('e3', 'Later', 2001),
                  kind: 'caused',
                  weight: 1,
                  direction: 'forward',
                ),
              ],
              onOpenEvent: (e) => opened.add(e.id),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Root event'), findsOneWidget);
      expect(find.text('Earlier'), findsOneWidget);
      expect(find.text('Later'), findsOneWidget);

      // Tapping a node fires onOpenEvent with that event id.
      await tester.tap(find.text('Later'));
      expect(opened, contains('e3'));
    });
  });

  group('showReactionSheet', () {
    testWidgets('opens a reaction sheet with the live reaction chips',
        (tester) async {
      final api = _api();
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (ctx) => ElevatedButton(
                onPressed: () => showReactionSheet(ctx, api, 'e1'),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      // The shared ReactionBar exposes keyed chips.
      expect(find.byKey(const Key('reaction-like')), findsOneWidget);
    });
  });

  test('formatLabel sanity (feed caption uses it)', () {
    expect(formatLabel(1989, TimePrecision.year), '1989');
  });
}
