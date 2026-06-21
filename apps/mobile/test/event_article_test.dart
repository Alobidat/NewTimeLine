// Tests for the standard event article (ADR-0021): the pure inline-link / clips-first
// helpers, plus a widget smoke test that the shared layout renders every standard
// section (title, summary, body, actors, the always-present related footer, sources).
// Network is faked via http's MockClient so no live API is needed.

import 'dart:convert';

import 'package:chronos_app/api/client.dart';
import 'package:chronos_app/api/models.dart';
import 'package:chronos_app/domain/time_format.dart';
import 'package:chronos_app/event/detail_widgets.dart';
import 'package:chronos_app/event/event_article.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

EventDetail _detail() => EventDetail(
  id: 'e1',
  title: 'Root event',
  summary: 'A neutral one-paragraph abstract.',
  body: 'The crisis followed the Earlier crisis directly.',
  tStart: 2011,
  tEnd: 2011,
  precision: TimePrecision.year,
  severity: 50,
  confidence: 80,
  sourceCount: 1,
  geoLabel: 'Tehran',
  category: 'conflict',
  entities: [
    EntityRole(
      entity: EntityRead(id: 'a1', kind: 'place', name: 'Iran'),
      role: 'location',
    ),
  ],
  sources: [
    SourceRead(
      id: 's1',
      url: 'https://example.com/a',
      domain: 'example.com',
      qualityScore: 70,
      title: 'A report',
    ),
  ],
);

EventRead _relatedEvent(String id, String title, double t) => EventRead(
  id: id,
  title: title,
  tStart: t,
  tEnd: t,
  precision: TimePrecision.year,
  severity: 30,
  confidence: 50,
  sourceCount: 1,
);

/// A MockClient that serves a fixed /related payload for any event id.
ApiClient _apiWithRelated(List<Map<String, dynamic>> related) {
  final mock = MockClient((req) async {
    if (req.url.path.endsWith('/related')) {
      return http.Response(jsonEncode(related), 200,
          headers: {'content-type': 'application/json'});
    }
    return http.Response('[]', 200,
        headers: {'content-type': 'application/json'});
  });
  return ApiClient(baseUrl: 'http://test', client: mock);
}

Map<String, dynamic> _relJson(EventRead e, String kind, String direction) => {
  'event': {
    'id': e.id,
    'title': e.title,
    't_start': e.tStart,
    't_end': e.tEnd,
    'time_precision': e.precision.name,
    'severity': e.severity,
    'confidence': e.confidence,
    'source_count': e.sourceCount,
  },
  'kind': kind,
  'weight': 1.0,
  'direction': direction,
};

void main() {
  group('orderMediaClipsFirst', () {
    MediaRead m(String id, String kind, String role) => MediaRead(
      id: id,
      kind: kind,
      role: role,
      disposition: 'archive',
      sensitivity: 0,
      locallyStored: true,
      status: 'ready',
    );

    test('puts a video clip first even when an image is hero-role', () {
      final ordered = orderMediaClipsFirst([
        m('img', 'image', 'hero'),
        m('vid', 'video', 'gallery'),
      ]);
      expect(ordered.first.id, 'vid');
    });

    test('hero-role wins within the same kind', () {
      final ordered = orderMediaClipsFirst([
        m('g', 'image', 'gallery'),
        m('h', 'image', 'hero'),
      ]);
      expect(ordered.first.id, 'h');
    });
  });

  group('buildBodySpans', () {
    test('links a related-event title named in the body', () {
      final related = [
        RelatedEvent(
          event: _relatedEvent('e2', 'Earlier crisis', 2010),
          kind: 'precursor',
          weight: 1,
          direction: 'back',
        ),
      ];
      final tapped = <String>[];
      final spans = buildBodySpans(
        body: 'The crisis followed the Earlier crisis directly.',
        related: related,
        linkColor: const Color(0xFF0000FF),
        onSelect: tapped.add,
      );
      // Find the linked span and fire its recognizer.
      final linked = spans
          .whereType<TextSpan>()
          .firstWhere((s) => s.text == 'Earlier crisis');
      expect(linked.recognizer, isA<TapGestureRecognizer>());
      (linked.recognizer as TapGestureRecognizer).onTap!();
      expect(tapped, ['e2']);
    });

    test('returns the body unchanged when nothing matches', () {
      final spans = buildBodySpans(
        body: 'No links here.',
        related: const [],
        linkColor: const Color(0xFF0000FF),
        onSelect: (_) {},
      );
      expect(spans.length, 1);
      expect((spans.single as TextSpan).text, 'No links here.');
    });
  });

  testWidgets('EventArticle renders the standard sections + related footer', (
    tester,
  ) async {
    final api = _apiWithRelated([
      _relJson(_relatedEvent('e2', 'Earlier crisis', 2010), 'precursor', 'back'),
      _relJson(_relatedEvent('e3', 'Aftermath', 2012), 'precursor', 'forward'),
      _relJson(_relatedEvent('e4', 'Nearby event', 2011), 'same-place', 'back'),
    ]);
    addTearDown(api.close);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: EventArticle(api: api, detail: _detail()),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Root event'), findsOneWidget);
    expect(find.text('A neutral one-paragraph abstract.'), findsOneWidget);
    expect(find.text('Iran · location'), findsOneWidget);
    expect(find.text('Related events'.toUpperCase()), findsOneWidget);
    expect(find.text('What led to this  (1)'), findsOneWidget);
    expect(find.text('What this caused  (1)'), findsOneWidget);
    expect(find.text('Same place / same actors  (1)'), findsOneWidget);
    // Sources sit at the bottom of the lazy ListView — scroll them into view first.
    // Target the outer article list (the related strips are also scrollables).
    await tester.scrollUntilVisible(
      find.text('A report'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('A report'), findsOneWidget);
  });
}
