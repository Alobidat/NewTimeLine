// Tests the feed top-bar account entry: when signed in it shows the user's profile picture
// (the Avatar widget — picture with an initials fallback), and when signed out it shows the
// outlined account icon as a sign-in affordance.

import 'dart:convert';

import 'package:chronos_app/api/client.dart';
import 'package:chronos_app/api/models.dart';
import 'package:chronos_app/feed/feed_home.dart';
import 'package:chronos_app/profile/avatar.dart';
import 'package:chronos_app/state/auth_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

ApiClient _emptyFeedApi() {
  final mock = MockClient((req) async {
    if (req.url.path.startsWith('/feed/')) {
      return http.Response(
        jsonEncode({'tab': 'foryou', 'items': [], 'next_cursor': null}),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    // me() / agreement / everything else: empty 200 so adopt()'s refresh is a harmless no-op.
    return http.Response('[]', 200, headers: {'content-type': 'application/json'});
  });
  return ApiClient(baseUrl: 'http://test', client: mock);
}

Finder _accountIcon() => find.descendant(
      of: find.byKey(const Key('account-entry')),
      matching: find.byType(Avatar),
    );

void main() {
  testWidgets('signed-in account button renders the profile avatar, not the person icon',
      (tester) async {
    final api = _emptyFeedApi();
    addTearDown(api.close);
    final auth = AuthState(api: api);
    await auth.adopt(AuthSession(
      token: 'jwt-1',
      user: SessionUser(
        id: 'u1',
        displayName: 'Omar Obidat',
        avatarUrl: 'https://example.com/me.jpg',
        emailVerified: true,
      ),
    ));

    await tester.pumpWidget(MaterialApp(home: FeedHome(api: api, auth: auth)));
    await tester.pump();

    expect(find.byKey(const Key('account-entry')), findsOneWidget);
    // The notifications bell appears when signed in.
    expect(find.byKey(const Key('notifications-bell')), findsOneWidget);
    expect(_accountIcon(), findsOneWidget); // the Avatar is shown
    // The signed-out person icon is NOT used inside the account button.
    expect(
      find.descendant(
        of: find.byKey(const Key('account-entry')),
        matching: find.byIcon(Icons.account_circle_outlined),
      ),
      findsNothing,
    );
    // The avatar carries the user's photo + name so it renders the picture (initials fallback).
    final avatar = tester.widget<Avatar>(_accountIcon());
    expect(avatar.url, 'https://example.com/me.jpg');
    expect(avatar.label, 'Omar Obidat');
  });

  testWidgets('signed-out account button renders the sign-in icon, not an avatar',
      (tester) async {
    final api = _emptyFeedApi();
    addTearDown(api.close);
    final auth = AuthState(api: api);

    await tester.pumpWidget(MaterialApp(home: FeedHome(api: api, auth: auth)));
    await tester.pump();

    // No bell when signed out.
    expect(find.byKey(const Key('notifications-bell')), findsNothing);
    expect(_accountIcon(), findsNothing);
    expect(
      find.descendant(
        of: find.byKey(const Key('account-entry')),
        matching: find.byIcon(Icons.account_circle_outlined),
      ),
      findsOneWidget,
    );
  });
}
