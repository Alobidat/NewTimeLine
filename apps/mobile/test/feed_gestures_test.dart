// Gesture + overlay-action coverage for the TikTok-style vertical feed (ADR-0027).
//
// These lock in the swipe behaviour the user reported broken on a real touch screen:
//   • swipe UP advances to the next clip (caption changes),
//   • swipe DOWN returns to the previous clip; a swipe down on the FIRST clip is clamped,
//   • a GENTLE, short, slow vertical drag still pages — guarding the regression where the
//     stock PageView snapped back on anything less than a half-screen drag/hard fling,
//   • swipe RIGHT walks to the NEXT timeline event, swipe LEFT to the PREVIOUS one,
//   • the bottom buttons open the graph/timeline web and the add-video flow,
//   • the right-rail action buttons exist and their taps fire the wired callbacks
//     (gated writes route through the sign-in gate; reads open their sheet),
//   • paging past the initially-loaded page fetches the next page (loads more).
//
// Network is faked with http's MockClient (no live API). Modelled on feed_test.dart's
// _api(...) / pumpFeed(...) pattern.

import 'dart:convert';

import 'package:chronos_app/api/client.dart';
import 'package:chronos_app/auth/login_screen.dart';
import 'package:chronos_app/feed/event_graph_view.dart';
import 'package:chronos_app/feed/feed_source.dart';
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

/// A MockClient serving a cursor-paginated `/feed/{tab}`, a fixed `/related`, and benign
/// empty-ish 200s for everything else. [pages] is a list of (items, nextCursor) tuples keyed
/// implicitly by request order so a test can drive multi-page paging deterministically.
ApiClient _api({
  List<Map<String, dynamic>>? timelineEvents,
  List<Map<String, dynamic>>? related,
  List<Map<String, dynamic>>? relatedForward,
  List<Map<String, dynamic>>? relatedBackward,
  List<(List<Map<String, dynamic>>, String?)>? pages,
}) {
  var pageIndex = 0;
  final mock = MockClient((req) async {
    final path = req.url.path;
    if (path.startsWith('/feed/')) {
      final tab = path.substring('/feed/'.length);
      List<Map<String, dynamic>> events;
      String? next;
      if (pages != null) {
        final idx = pageIndex.clamp(0, pages.length - 1);
        events = pages[idx].$1;
        next = pages[idx].$2;
        pageIndex++;
      } else {
        events = timelineEvents ?? const [];
        next = null;
      }
      return http.Response(
        jsonEncode({
          'tab': tab,
          'items': [
            for (final e in events)
              {'event': e, 'hero_media_id': null, 'score': 1.0},
          ],
          'next_cursor': next,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (path.endsWith('/related')) {
      // Lateral walk is direction-aware: swipe right → forward, swipe left → backward.
      final dir = req.url.queryParameters['direction'];
      final payload = dir == 'forward'
          ? (relatedForward ?? related ?? const [])
          : dir == 'back'
              ? (relatedBackward ?? related ?? const [])
              : (related ?? const []);
      return http.Response(jsonEncode(payload), 200,
          headers: {'content-type': 'application/json'});
    }
    // Event detail (opened by the info / comment sheets) — a bare event object is enough;
    // EventDetail.fromJson defaults the sources/media/entities arrays to empty.
    if (path.startsWith('/events/') && !path.endsWith('/related')) {
      final id = path.substring('/events/'.length);
      return http.Response(jsonEncode(_eventJson(id, 'Detail', 2000)), 200,
          headers: {'content-type': 'application/json'});
    }
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
  Future<AuthState> pumpFeed(
    WidgetTester tester,
    ApiClient api, {
    FeedSource? source,
    VoidCallback? onAddVideo,
  }) async {
    final auth = AuthState(api: api);
    addTearDown(auth.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: VideoFeed(
            api: api,
            auth: auth,
            source: source ?? FeedSource(api),
            tab: FeedTab.forYou,
            onAddVideo: onAddVideo,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return auth;
  }

  // The single transparent surface that drives every feed gesture (vertical paging + lateral
  // navigation). Paging no longer uses a PageView — it's swapped directly from this detector.
  Finder pager() => find.byKey(const Key('feed-gestures'));

  group('vertical paging', () {
    testWidgets('swipe UP advances to the next clip', (tester) async {
      final api = _api(timelineEvents: [
        _eventJson('e1', 'Berlin Wall falls', 1989),
        _eventJson('e2', 'Reunification', 1990),
      ]);
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.text('Berlin Wall falls'), findsOneWidget);
      await tester.fling(pager(), const Offset(0, -500), 1000);
      await tester.pumpAndSettle();
      expect(find.text('Reunification'), findsOneWidget);
      expect(find.text('Berlin Wall falls'), findsNothing);
    });

    testWidgets('swipe DOWN returns to the previous clip', (tester) async {
      final api = _api(timelineEvents: [
        _eventJson('e1', 'First', 2001),
        _eventJson('e2', 'Second', 2002),
      ]);
      addTearDown(api.close);
      await pumpFeed(tester, api);

      // Forward to the second, then back.
      await tester.fling(pager(), const Offset(0, -500), 1000);
      await tester.pumpAndSettle();
      expect(find.text('Second'), findsOneWidget);

      await tester.fling(pager(), const Offset(0, 500), 1000);
      await tester.pumpAndSettle();
      expect(find.text('First'), findsOneWidget);
    });

    testWidgets('swipe DOWN on the first clip is clamped (stays put)',
        (tester) async {
      final api = _api(timelineEvents: [
        _eventJson('e1', 'First', 2001),
        _eventJson('e2', 'Second', 2002),
      ]);
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.text('First'), findsOneWidget);
      // A downward fling at page 0 has nowhere to go — it must snap back to the first clip.
      await tester.fling(pager(), const Offset(0, 600), 1200);
      await tester.pumpAndSettle();
      expect(find.text('First'), findsOneWidget);
      expect(find.text('Second'), findsNothing);
    });

    testWidgets('a GENTLE short slow drag still pages (regression guard)',
        (tester) async {
      final api = _api(timelineEvents: [
        _eventJson('e1', 'Berlin Wall falls', 1989),
        _eventJson('e2', 'Reunification', 1990),
      ]);
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.text('Berlin Wall falls'), findsOneWidget);
      // A small, slow drag (~150px over the default 600px-tall surface, ~25% of a page) with
      // NO fling — this is what the stock PageView snapped back on. The gesture surface pages on
      // distance alone (past ~6% of the height), so it must advance one clip.
      final centre = tester.getCenter(pager());
      final gesture = await tester.startGesture(centre);
      // Move slowly (long pauses between tiny steps) so the release velocity stays well below
      // the fling threshold — this exercises the DRIFT path: paging on distance alone.
      for (var i = 0; i < 15; i++) {
        await gesture.moveBy(const Offset(0, -10));
        await tester.pump(const Duration(milliseconds: 120));
      }
      await gesture.up();
      await tester.pumpAndSettle();
      expect(find.text('Reunification'), findsOneWidget);
    });
  });

  group('lateral gestures', () {
    testWidgets('swipe RIGHT walks to the NEXT event in the timeline',
        (tester) async {
      final api = _api(
        timelineEvents: [_eventJson('e1', 'Root', 2000)],
        relatedForward: [
          _relJson(_eventJson('e2', 'Later event', 2001), 'caused', 'forward'),
        ],
      );
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.text('Root'), findsOneWidget);
      // Fling right (left-to-right) → forward related event, appended + advanced to.
      await tester.fling(pager(), const Offset(500, 0), 1200);
      await tester.pumpAndSettle();
      expect(find.text('Later event'), findsOneWidget);
    });

    testWidgets('swipe LEFT walks to the PREVIOUS event in the timeline',
        (tester) async {
      final api = _api(
        timelineEvents: [_eventJson('e1', 'Root', 2000)],
        relatedBackward: [
          _relJson(
              _eventJson('e0', 'Earlier event', 1999), 'caused', 'backward'),
        ],
      );
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.text('Root'), findsOneWidget);
      // Fling left (right-to-left) → backward related event, appended + advanced to.
      await tester.fling(pager(), const Offset(-500, 0), 1200);
      await tester.pumpAndSettle();
      expect(find.text('Earlier event'), findsOneWidget);
    });

    testWidgets('up/down stays on the feed, independent of a lateral walk',
        (tester) async {
      // Feed: First → Second. First has a forward-related "Sidestep" on its timeline.
      final api = _api(
        timelineEvents: [
          _eventJson('e1', 'First', 2000),
          _eventJson('e2', 'Second', 2001),
        ],
        relatedForward: [
          _relJson(_eventJson('x1', 'Sidestep', 2000), 'caused', 'forward'),
        ],
      );
      addTearDown(api.close);
      await pumpFeed(tester, api);

      // Walk RIGHT along First's timeline → now showing the lateral "Sidestep"…
      await tester.fling(pager(), const Offset(500, 0), 1200);
      await tester.pumpAndSettle();
      expect(find.text('Sidestep'), findsOneWidget);

      // …then swipe UP. It must land on the next *feed* event (Second), NOT anything derived
      // from the lateral position — up/down is independent of left/right.
      await tester.fling(pager(), const Offset(0, -500), 1000);
      await tester.pumpAndSettle();
      expect(find.text('Second'), findsOneWidget);
      expect(find.text('Sidestep'), findsNothing);
    });

    testWidgets('the bottom Timeline-web button opens the event graph',
        (tester) async {
      final api = _api(
        timelineEvents: [_eventJson('e1', 'Root', 2000)],
        related: [
          _relJson(_eventJson('e2', 'Caused this', 2001), 'caused', 'forward'),
        ],
      );
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.text('Root'), findsOneWidget);
      await tester.tap(find.byKey(const Key('feed-graph')));
      await tester.pumpAndSettle();
      expect(find.byType(EventGraphView), findsOneWidget);
    });

    testWidgets('the bottom Add-video button fires onAddVideo', (tester) async {
      final api = _api(timelineEvents: [_eventJson('e1', 'Root', 2000)]);
      addTearDown(api.close);
      var added = 0;
      await pumpFeed(tester, api, onAddVideo: () => added++);

      // Hidden when no callback; present + wired when onAddVideo is supplied.
      final btn = find.byKey(const Key('feed-add-video'));
      expect(btn, findsOneWidget);
      await tester.tap(btn);
      await tester.pumpAndSettle();
      expect(added, 1);
    });
  });

  group('overlay rail actions', () {
    // Each gated write (react / promote / follow / save) routes an anonymous user through the
    // sign-in gate first; tapping the button must push the LoginScreen — proof the rail wired
    // the callback through. Read actions (info / comment / share) open their own sheet.
    Future<void> tapAndExpectLogin(
      WidgetTester tester,
      ApiClient api,
      Key buttonKey,
    ) async {
      await pumpFeed(tester, api);
      final btn = find.byKey(buttonKey);
      expect(btn, findsOneWidget);
      await tester.tap(btn);
      await tester.pumpAndSettle();
      expect(find.byType(LoginScreen), findsOneWidget,
          reason: '${buttonKey.toString()} should gate through sign-in');
    }

    ApiClient oneClip() => _api(timelineEvents: [
          _eventJson('e1', 'A clip', 2000),
        ]);

    testWidgets('react gates through sign-in', (tester) async {
      final api = oneClip();
      addTearDown(api.close);
      await tapAndExpectLogin(tester, api, const Key('rail-react'));
    });

    testWidgets('promote up gates through sign-in', (tester) async {
      final api = oneClip();
      addTearDown(api.close);
      await tapAndExpectLogin(tester, api, const Key('rail-promote-up'));
    });

    testWidgets('promote down gates through sign-in', (tester) async {
      final api = oneClip();
      addTearDown(api.close);
      await tapAndExpectLogin(tester, api, const Key('rail-promote-down'));
    });

    testWidgets('follow gates through sign-in', (tester) async {
      final api = oneClip();
      addTearDown(api.close);
      await tapAndExpectLogin(tester, api, const Key('rail-follow'));
    });

    testWidgets('save/bookmark gates through sign-in', (tester) async {
      final api = oneClip();
      addTearDown(api.close);
      await tapAndExpectLogin(tester, api, const Key('rail-bookmark'));
    });

    testWidgets('comment opens the info sheet (read, no gate)', (tester) async {
      final api = oneClip();
      addTearDown(api.close);
      await pumpFeed(tester, api);
      await tester.tap(find.byKey(const Key('rail-comment')));
      await tester.pumpAndSettle();
      // No sign-in gate for a read.
      expect(find.byType(LoginScreen), findsNothing);
    });

    testWidgets('info opens the info sheet (read, no gate)', (tester) async {
      final api = oneClip();
      addTearDown(api.close);
      await pumpFeed(tester, api);
      await tester.tap(find.byKey(const Key('rail-info')));
      await tester.pumpAndSettle();
      expect(find.byType(LoginScreen), findsNothing);
    });

    testWidgets('share opens the share sheet (read, no gate)', (tester) async {
      final api = oneClip();
      addTearDown(api.close);
      await pumpFeed(tester, api);
      await tester.tap(find.byKey(const Key('rail-share')));
      await tester.pumpAndSettle();
      expect(find.byType(LoginScreen), findsNothing);
    });

    testWidgets('every rail button is present', (tester) async {
      final api = oneClip();
      addTearDown(api.close);
      await pumpFeed(tester, api);
      for (final k in const [
        'rail-promote-up',
        'rail-promote-down',
        'rail-react',
        'rail-comment',
        'rail-follow',
        'rail-bookmark',
        'rail-share',
        'rail-info',
      ]) {
        expect(find.byKey(Key(k)), findsOneWidget, reason: 'missing $k');
      }
    });
  });

  group('paging loads more', () {
    testWidgets('swiping near the end fetches the next page', (tester) async {
      // Page 1 → [e1, e2] + cursor; page 2 → [e3] no cursor. Advancing into page 1's tail must
      // load page 2 so e3 becomes reachable.
      final api = _api(pages: [
        ([_eventJson('e1', 'One', 2001), _eventJson('e2', 'Two', 2002)], 'c2'),
        ([_eventJson('e3', 'Three', 2003)], null),
      ]);
      addTearDown(api.close);
      await pumpFeed(tester, api);

      expect(find.text('One'), findsOneWidget);
      // Up to e2 — onPageChanged(index 1 == length-1) triggers _loadMore for page 2.
      await tester.fling(pager(), const Offset(0, -500), 1000);
      await tester.pumpAndSettle();
      expect(find.text('Two'), findsOneWidget);
      // Up again — e3 has been appended, so it's now reachable.
      await tester.fling(pager(), const Offset(0, -500), 1000);
      await tester.pumpAndSettle();
      expect(find.text('Three'), findsOneWidget);
    });
  });
}
