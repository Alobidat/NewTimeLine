// Tests for the Upload screen's device-clip capture path (Creator Studio Phase 1). The platform
// picker is injected via `pickClip`, so these run on the VM without a real browser/camera.

import 'dart:typed_data';

import 'package:chronos_app/api/client.dart';
import 'package:chronos_app/state/auth_state.dart';
import 'package:chronos_app/upload/clip_source.dart';
import 'package:chronos_app/upload/upload_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

ApiClient _api() =>
    ApiClient(baseUrl: 'http://test', client: MockClient((_) async => http.Response('{}', 200)));

Widget _host(UploadScreen screen) => MaterialApp(home: screen);

void main() {
  testWidgets('capture buttons show, and a picked clip becomes a chip (URL field hidden)',
      (tester) async {
    final clip = PickedClip(
      bytes: Uint8List.fromList(List.filled(2 * 1024 * 1024, 7)), // 2 MB
      filename: 'my-take.webm',
      mime: 'video/webm',
    );
    final api = _api();
    addTearDown(api.close);
    // Tall surface so every form field in the lazy ListView is built (no scrolling needed).
    await tester.binding.setSurfaceSize(const Size(1200, 2600));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_host(UploadScreen(
      api: api,
      auth: AuthState(api: api),
      captureSupported: true, // force the web capture UI on the test VM
      pickClip: ({bool fromCamera = false}) async => clip,
    )));

    // Capture affordances present; the URL field is the fallback and visible until a clip exists.
    expect(find.byKey(const Key('upload-record')), findsOneWidget);
    expect(find.byKey(const Key('upload-choose')), findsOneWidget);
    expect(find.byKey(const Key('upload-source-url')), findsOneWidget);

    // Pick a clip → it shows as a chip with its name + size, and the URL field disappears.
    await tester.tap(find.byKey(const Key('upload-record')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('upload-clip-chip')), findsOneWidget);
    expect(find.text('my-take.webm'), findsOneWidget);
    expect(find.text('2.0 MB'), findsOneWidget);
    expect(find.byKey(const Key('upload-source-url')), findsNothing);

    // Clearing it returns to the record/choose + URL state.
    await tester.tap(find.byKey(const Key('upload-clip-clear')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('upload-clip-chip')), findsNothing);
    expect(find.byKey(const Key('upload-source-url')), findsOneWidget);
  });

  testWidgets('reply mode pre-links the parent event and shows a reply banner',
      (tester) async {
    final api = _api();
    addTearDown(api.close);
    await tester.binding.setSurfaceSize(const Size(1200, 2600));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_host(UploadScreen(
      api: api,
      auth: AuthState(api: api),
      captureSupported: false,
      replyToEventId: 'evt-parent-123',
      replyToTitle: 'The Berlin Wall falls',
    )));

    // A banner names what's being replied to, and the required link is pre-filled with the parent.
    expect(find.byKey(const Key('upload-reply-banner')), findsOneWidget);
    expect(find.textContaining('The Berlin Wall falls'), findsOneWidget);
    expect(find.text('evt-parent-123'), findsOneWidget); // pre-filled in the links field
  });

  testWidgets('without capture support, only the URL path is offered', (tester) async {
    final api = _api();
    addTearDown(api.close);
    await tester.pumpWidget(_host(UploadScreen(
      api: api,
      auth: AuthState(api: api),
      captureSupported: false,
    )));
    expect(find.byKey(const Key('upload-record')), findsNothing);
    expect(find.byKey(const Key('upload-source-url')), findsOneWidget);
  });
}
