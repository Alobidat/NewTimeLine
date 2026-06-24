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

      // The active page's caption + the always-present rail buttons (react/comment/save/share).
      expect(find.text('Berlin Wall falls'), findsOneWidget);
      expect(find.byKey(const Key('rail-react')), findsOneWidget);
      expect(find.byKey(const Key('rail-comment')), findsOneWidget);
      expect(find.byKey(const Key('rail-bookmark')), findsOneWidget);
      expect(find.byKey(const Key('rail-share')), findsOneWidget);
      // Removed in the rail redesign: promote/demote (folded into React long-press), follow
      // (moved onto the avatar), info (moved to the caption "…more").
      expect(find.byKey(const Key('rail-promote-up')), findsNothing);
      expect(find.byKey(const Key('rail-info')), findsNothing);
      // No author on these seed events → no avatar block.
      expect(find.byKey(const Key('rail-author')), findsNothing);
    });

    testWidgets('an authored clip shows the avatar, follow badge + caption "…more"',
        (tester) async {
      // A user-generated clip carries an author + summary → the rail leads with the avatar
      // (with a "+" follow badge since the caller doesn't follow them) and the caption shows
      // the description with a tappable "…more" (the info action moved here from the rail).
      final mock = MockClient((req) async {
        if (req.url.path.startsWith('/feed/')) {
          return http.Response(
            jsonEncode({
              'tab': 'foryou',
              'items': [
                {
                  'event': {
                    ..._eventJson('e1', 'Jane films a rocket', 2025),
                    'summary': 'A long behind-the-scenes look at the launch pad and crew.',
                    'author_id': 'u9',
                  },
                  'hero_media_id': null,
                  'hero_is_clip': true,
                  'author': {
                    'id': 'u9',
                    'handle': 'jane',
                    'display_name': 'Jane Doe',
                    'avatar_url': null,
                  },
                  'score': 1.0,
                },
              ],
              'next_cursor': null,
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        // Rail-state fetches (stats/reactions/promote/follow) degrade gracefully to defaults.
        return http.Response('[]', 200, headers: {'content-type': 'application/json'});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.byKey(const Key('rail-author')), findsOneWidget);
      expect(find.byKey(const Key('rail-follow-badge')), findsOneWidget);
      expect(find.byKey(const Key('caption-more')), findsOneWidget);
      // The author is also attributed in the caption (@handle), tappable to their profile.
      expect(find.byKey(const Key('caption-author')), findsOneWidget);
      expect(find.text('@jane'), findsOneWidget);
    });

    testWidgets('an agent clip is attributed to its entity (avatar + follow, no @)',
        (tester) async {
      // A NASA world-event clip has no user uploader (author_id null) but is attributed to the
      // entity NASA, so the avatar + follow badge still show and the caption names it (no "@").
      final mock = MockClient((req) async {
        if (req.url.path.startsWith('/feed/')) {
          return http.Response(
            jsonEncode({
              'tab': 'foryou',
              'items': [
                {
                  'event': _eventJson('e1', 'Apollo 11 Plaque', 1969), // no author_id
                  'hero_media_id': null,
                  'hero_is_clip': true,
                  'author': {'id': 'ent-nasa', 'handle': 'nasa', 'display_name': 'NASA'},
                  'author_kind': 'entity',
                  'score': 1.0,
                },
              ],
              'next_cursor': null,
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('[]', 200, headers: {'content-type': 'application/json'});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.byKey(const Key('rail-author')), findsOneWidget);
      expect(find.byKey(const Key('rail-follow-badge')), findsOneWidget);
      // Entity attribution names the entity without an "@" handle.
      expect(find.text('NASA'), findsOneWidget);
      expect(find.text('@nasa'), findsNothing);
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

  group('showReactSelector (lift-up menu)', () {
    testWidgets('offers the three mutually-exclusive choices + returns the pick',
        (tester) async {
      ReactChoice? picked;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (ctx) => ElevatedButton(
                onPressed: () async => picked = await showReactSelector(
                    ctx, ReactState.none, const Offset(200, 400)),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      // Love / Promote / Demote items are present in the anchored popup menu.
      expect(find.byKey(const Key('react-choice-love')), findsOneWidget);
      expect(find.byKey(const Key('react-choice-promote')), findsOneWidget);
      expect(find.byKey(const Key('react-choice-demote')), findsOneWidget);
      // Picking Promote returns that choice to the caller.
      await tester.tap(find.byKey(const Key('react-choice-promote')));
      await tester.pumpAndSettle();
      expect(picked, ReactChoice.promote);
    });

    testWidgets('share menu offers repost + share link', (tester) async {
      ShareChoice? picked;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (ctx) => ElevatedButton(
                onPressed: () async => picked = await showShareSelector(
                    ctx, const Offset(200, 400), reposted: false),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('share-choice-repost')), findsOneWidget);
      expect(find.byKey(const Key('share-choice-link')), findsOneWidget);
      await tester.tap(find.byKey(const Key('share-choice-repost')));
      await tester.pumpAndSettle();
      expect(picked, ShareChoice.repost);
    });
  });

  test('formatLabel sanity (feed caption uses it)', () {
    expect(formatLabel(1989, TimePrecision.year), '1989');
  });
}
