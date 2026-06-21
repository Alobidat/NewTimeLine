// Tests for the Phase 3d-IU interaction UI (ADR-0025): the reaction bar's optimistic
// toggle and server reconcile, and the threaded comments tree + composer. Network is
// faked via http's MockClient so no live API is needed.

import 'dart:convert';

import 'package:chronos_app/api/client.dart';
import 'package:chronos_app/api/models.dart';
import 'package:chronos_app/event/comment_tile.dart';
import 'package:chronos_app/event/comments_section.dart';
import 'package:chronos_app/event/reaction_bar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

CommentRead _comment(
  String id,
  String body, {
  String? parentId,
  String status = 'visible',
}) => CommentRead(
  id: id,
  eventId: 'e1',
  userId: 'u1',
  parentId: parentId,
  body: body,
  score: 0,
  status: status,
  createdAt: DateTime.utc(2026, 1, 1),
  updatedAt: DateTime.utc(2026, 1, 1),
);

void main() {
  group('buildCommentTree', () {
    test('nests replies under their parent in arrival order', () {
      final tree = buildCommentTree([
        _comment('a', 'root A'),
        _comment('b', 'reply to A', parentId: 'a'),
        _comment('c', 'root C'),
        _comment('d', 'reply to B', parentId: 'b'),
      ]);
      expect(tree.length, 2); // a, c
      final a = tree.first;
      expect(a.comment.id, 'a');
      expect(a.replies.length, 1);
      expect(a.replies.first.comment.id, 'b');
      expect(a.replies.first.replies.single.comment.id, 'd');
    });

    test('orphan replies (missing parent) surface at the root', () {
      final tree = buildCommentTree([
        _comment('x', 'orphan', parentId: 'gone'),
      ]);
      expect(tree.single.comment.id, 'x');
    });
  });

  testWidgets('ReactionBar toggles optimistically then reconciles', (
    tester,
  ) async {
    var posted = 0;
    final mock = MockClient((req) async {
      if (req.method == 'GET' && req.url.path.endsWith('/reactions')) {
        return http.Response(
          jsonEncode({
            'event_id': 'e1',
            'counts': {'like': 2},
            'mine': <String>[],
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (req.method == 'POST' && req.url.path.endsWith('/reactions')) {
        posted++;
        // Server says the like is now active and the count is 3.
        return http.Response(
          jsonEncode({
            'kind': 'like',
            'active': true,
            'counts': {'like': 3},
            'mine': ['like'],
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('{}', 200,
          headers: {'content-type': 'application/json'});
    });
    final api = ApiClient(baseUrl: 'http://test', client: mock);
    addTearDown(api.close);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ReactionBar(api: api, eventId: 'e1')),
      ),
    );
    await tester.pumpAndSettle();

    // Initial aggregate: like 2, not mine.
    expect(find.text('Like  2'), findsOneWidget);

    await tester.tap(find.byKey(const Key('reaction-like')));
    await tester.pump(); // optimistic frame: count nudges to 3 before the POST resolves
    expect(find.text('Like  3'), findsOneWidget);

    await tester.pumpAndSettle(); // POST resolves; reconciles to the server aggregate
    expect(posted, 1);
    expect(find.text('Like  3'), findsOneWidget);
  });

  testWidgets('CommentsSection renders the tree and posts a top-level comment', (
    tester,
  ) async {
    var created = 0;
    var listCalls = 0;
    final mock = MockClient((req) async {
      final p = req.url.path;
      if (req.method == 'GET' && p.endsWith('/comments')) {
        listCalls++;
        // First load: one root + one reply. After a post, include the new comment.
        final base = [
          _comment('c1', 'First comment'),
          _comment('c2', 'A reply', parentId: 'c1'),
        ];
        final list = [
          for (final c in base)
            {
              'id': c.id,
              'event_id': c.eventId,
              'user_id': c.userId,
              'parent_id': c.parentId,
              'body': c.body,
              'score': c.score,
              'status': c.status,
              'created_at': c.createdAt.toIso8601String(),
              'updated_at': c.updatedAt.toIso8601String(),
            },
          if (created > 0)
            {
              'id': 'c3',
              'event_id': 'e1',
              'user_id': 'u1',
              'parent_id': null,
              'body': 'Brand new comment',
              'score': 0,
              'status': 'visible',
              'created_at': DateTime.utc(2026, 2, 1).toIso8601String(),
              'updated_at': DateTime.utc(2026, 2, 1).toIso8601String(),
            },
        ];
        return http.Response(jsonEncode(list), 200,
            headers: {'content-type': 'application/json'});
      }
      if (req.method == 'POST' && p.endsWith('/comments')) {
        created++;
        return http.Response(
          jsonEncode({
            'id': 'c3',
            'event_id': 'e1',
            'user_id': 'u1',
            'parent_id': null,
            'body': 'Brand new comment',
            'score': 0,
            'status': 'visible',
            'created_at': DateTime.utc(2026, 2, 1).toIso8601String(),
            'updated_at': DateTime.utc(2026, 2, 1).toIso8601String(),
          }),
          201,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('{}', 200,
          headers: {'content-type': 'application/json'});
    });
    final api = ApiClient(baseUrl: 'http://test', client: mock);
    addTearDown(api.close);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: CommentsSection(api: api, eventId: 'e1'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // The tree renders the root and the (indented) reply.
    expect(find.text('First comment'), findsOneWidget);
    expect(find.text('A reply'), findsOneWidget);
    // The reply tile is rendered as a nested CommentTile.
    expect(find.byType(CommentTile), findsNWidgets(2));

    // Post a top-level comment via the root composer.
    await tester.enterText(
      find.descendant(
        of: find.byKey(const Key('comment-composer-root')),
        matching: find.byType(TextField),
      ),
      'Brand new comment',
    );
    await tester.tap(
      find.descendant(
        of: find.byKey(const Key('comment-composer-root')),
        matching: find.text('Post'),
      ),
    );
    await tester.pumpAndSettle();

    expect(created, 1);
    expect(listCalls, greaterThanOrEqualTo(2)); // reloaded after the post
    expect(find.text('Brand new comment'), findsOneWidget);
  });
}
