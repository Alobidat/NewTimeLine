// Tests for the Phase 4-G auth/account UI (ADR-0026): the session/Bearer wiring on
// AuthState + ApiClient, the provider-list login screen (incl. the empty case), the
// agreement consent gate, and the account screen's export + delete actions. Network is
// faked via http's MockClient.

import 'dart:convert';

import 'package:chronos_app/account/account_screen.dart';
import 'package:chronos_app/api/client.dart';
import 'package:chronos_app/api/models.dart';
import 'package:chronos_app/auth/agreement_screen.dart';
import 'package:chronos_app/auth/login_screen.dart';
import 'package:chronos_app/auth/oauth_flow.dart';
import 'package:chronos_app/state/auth_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response _json(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json'},
);

void main() {
  group('AuthState + Bearer wiring', () {
    test('adopt() attaches the Bearer; signOut() clears it', () async {
      String? sawAuthHeader;
      final mock = MockClient((req) async {
        sawAuthHeader = req.headers['authorization'];
        if (req.url.path == '/account/me') {
          return _json({'id': 'u1', 'email': 'a@b.c', 'email_verified': true});
        }
        if (req.url.path == '/auth/agreement/status') {
          return _json({'accepted': true});
        }
        return _json({});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);
      final auth = AuthState(api: api);

      expect(api.sessionToken, isNull);
      await auth.adopt(AuthSession(
        token: 'jwt-123',
        user: SessionUser(id: 'u1', email: 'a@b.c', emailVerified: true),
      ));

      expect(api.sessionToken, 'jwt-123');
      expect(auth.isSignedIn, isTrue);
      // refresh() fired a request carrying the Bearer.
      expect(sawAuthHeader, 'Bearer jwt-123');
      // me() verified + agreement accepted → can interact.
      expect(auth.canInteract, isTrue);

      await auth.signOut();
      expect(api.sessionToken, isNull);
      expect(auth.isSignedIn, isFalse);
      expect(auth.canInteract, isFalse);
    });

    test('anonymous reads send no Authorization header', () async {
      String? sawAuthHeader = 'unset';
      final mock = MockClient((req) async {
        sawAuthHeader = req.headers['authorization'];
        return _json([]);
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);
      await api.entities();
      expect(sawAuthHeader, isNull);
    });
  });

  group('runOAuthFlow', () {
    test('exchanges the prompted code for a session JWT', () async {
      Map<String, dynamic>? callbackBody;
      final mock = MockClient((req) async {
        if (req.url.path == '/auth/google/login') {
          return _json({
            'authorize_url': 'https://idp/authorize?x=1',
            'state': 'st-9',
            'code_verifier': 'pkce-abc',
          });
        }
        if (req.url.path == '/auth/google/callback') {
          callbackBody = jsonDecode(req.body) as Map<String, dynamic>;
          return _json({
            'token': 'jwt-xyz',
            'user': {'id': 'u9', 'email': 'z@z.z', 'email_verified': true},
          });
        }
        return _json({});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);

      final session = await runOAuthFlow(
        api,
        'google',
        prompter: (challenge) async {
          expect(challenge.authorizeUrl, contains('authorize'));
          expect(challenge.codeVerifier, 'pkce-abc');
          return (code: 'auth-code-1', state: challenge.state);
        },
      );

      expect(session, isNotNull);
      expect(session!.token, 'jwt-xyz');
      expect(session.user?.id, 'u9');
      expect(callbackBody?['code'], 'auth-code-1');
      expect(callbackBody?['state'], 'st-9');
      expect(callbackBody?['code_verifier'], 'pkce-abc');
    });

    test('returns null when the user cancels', () async {
      final mock = MockClient((req) async {
        if (req.url.path == '/auth/google/login') {
          return _json({'authorize_url': 'https://idp/authorize'});
        }
        return _json({});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);

      final session =
          await runOAuthFlow(api, 'google', prompter: (_) async => null);
      expect(session, isNull);
    });
  });

  group('LoginScreen', () {
    testWidgets('renders a button per provider', (tester) async {
      final mock = MockClient((req) async {
        if (req.url.path == '/auth/providers') {
          return _json({
            'providers': [
              {'name': 'google', 'display_name': 'Google'},
              {'name': 'apple'},
            ],
          });
        }
        return _json({});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);
      final auth = AuthState(api: api);

      await tester.pumpWidget(
        MaterialApp(home: LoginScreen(api: api, auth: auth)),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('provider-google')), findsOneWidget);
      expect(find.byKey(const Key('provider-apple')), findsOneWidget);
      expect(find.text('Continue with Google'), findsOneWidget);
      // display_name absent → title-cased name.
      expect(find.text('Continue with Apple'), findsOneWidget);
    });

    testWidgets('empty provider list shows the configured-message, no buttons',
        (tester) async {
      final mock = MockClient((req) async {
        if (req.url.path == '/auth/providers') {
          return _json({'providers': <Object>[]});
        }
        return _json({});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);
      final auth = AuthState(api: api);

      await tester.pumpWidget(
        MaterialApp(home: LoginScreen(api: api, auth: auth)),
      );
      await tester.pumpAndSettle();

      expect(find.text('No sign-in providers configured'), findsOneWidget);
      expect(find.byType(FilledButton), findsNothing);
    });
  });

  group('AgreementScreen (consent gate)', () {
    testWidgets('Accept posts to /auth/agreement/accept and marks accepted',
        (tester) async {
      var accepted = 0;
      String? acceptedVersion;
      final mock = MockClient((req) async {
        if (req.url.path == '/auth/agreement') {
          return _json({'version': 'v2', 'summary': 'Be nice.'});
        }
        if (req.method == 'POST' && req.url.path == '/auth/agreement/accept') {
          accepted++;
          acceptedVersion =
              (jsonDecode(req.body) as Map<String, dynamic>)['version'] as String?;
          return _json({});
        }
        return _json({});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);
      final auth = AuthState(api: api);

      await tester.pumpWidget(
        MaterialApp(home: AgreementScreen(api: api, auth: auth)),
      );
      await tester.pumpAndSettle();

      expect(find.text('Version v2'), findsOneWidget);
      expect(auth.agreementAccepted, isFalse);

      await tester.tap(find.byKey(const Key('accept-agreement')));
      await tester.pumpAndSettle();

      expect(accepted, 1);
      expect(acceptedVersion, 'v2');
      expect(auth.agreementAccepted, isTrue);
    });
  });

  group('AccountScreen GDPR actions', () {
    Future<AuthState> signedIn(ApiClient api) async {
      final auth = AuthState(api: api);
      await auth.adopt(AuthSession(
        token: 'jwt',
        user: SessionUser(id: 'u1', email: 'a@b.c', emailVerified: true),
      ));
      return auth;
    }

    testWidgets('Download my data fetches /account/export', (tester) async {
      var exported = 0;
      final mock = MockClient((req) async {
        if (req.url.path == '/account/me') {
          return _json({'id': 'u1', 'email': 'a@b.c', 'email_verified': true});
        }
        if (req.url.path == '/auth/agreement/status') return _json({'accepted': true});
        if (req.url.path == '/account/export') {
          exported++;
          return _json({'user': 'u1', 'comments': []});
        }
        return _json({});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);
      final auth = await signedIn(api);

      await tester.pumpWidget(
        MaterialApp(home: AccountScreen(api: api, auth: auth)),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('download-data')));
      await tester.pumpAndSettle();

      expect(exported, 1);
      expect(find.text('Your data export'), findsOneWidget);
    });

    testWidgets('Delete my account confirms then DELETEs /account and signs out',
        (tester) async {
      var deleted = 0;
      final mock = MockClient((req) async {
        if (req.url.path == '/account/me') {
          return _json({'id': 'u1', 'email': 'a@b.c', 'email_verified': true});
        }
        if (req.url.path == '/auth/agreement/status') return _json({'accepted': true});
        if (req.method == 'DELETE' && req.url.path == '/account') {
          deleted++;
          return _json({});
        }
        return _json({});
      });
      final api = ApiClient(baseUrl: 'http://test', client: mock);
      addTearDown(api.close);
      final auth = await signedIn(api);

      await tester.pumpWidget(
        MaterialApp(home: AccountScreen(api: api, auth: auth)),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('delete-account')));
      await tester.pumpAndSettle();
      // Confirm in the dialog.
      await tester.tap(find.byKey(const Key('confirm-delete')));
      await tester.pumpAndSettle();

      expect(deleted, 1);
      expect(api.sessionToken, isNull);
      expect(auth.isSignedIn, isFalse);
      // Back to the anonymous body.
      expect(find.byKey(const Key('account-sign-in')), findsOneWidget);
    });
  });
}
