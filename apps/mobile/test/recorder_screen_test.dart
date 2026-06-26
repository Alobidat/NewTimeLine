// Tests the in-app recorder screen's state machine with a fake controller (no real camera /
// interop) — record→stop returns a clip, and an unavailable camera offers the file fallback.

import 'dart:typed_data';

import 'package:chronos_app/creator/recorder_controller.dart';
import 'package:chronos_app/creator/recorder_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeRecorder implements RecorderController {
  _FakeRecorder({required this.available, this.result});

  final bool available;
  final PickedClip? result;
  bool _recording = false;

  @override
  Future<bool> initPreview({bool front = true}) async => available;

  @override
  Widget buildPreview() => const ColoredBox(color: Colors.black);

  @override
  bool get canSwitchCamera => true;

  @override
  bool get isRecording => _recording;

  @override
  void startRecording() => _recording = true;

  @override
  Future<PickedClip?> stopRecording() async {
    _recording = false;
    return result;
  }

  @override
  Future<bool> switchCamera() async => true;

  @override
  void dispose() {}
}

void main() {
  testWidgets('unavailable camera shows the file fallback and pops null', (tester) async {
    PickedClip? popped;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (ctx) => Scaffold(
          body: ElevatedButton(
            onPressed: () async {
              popped = await Navigator.of(ctx).push<PickedClip?>(MaterialPageRoute(
                builder: (_) => const RecorderScreen(controller: _Unavailable()),
              ));
            },
            child: const Text('go'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('go'));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('recorder-fallback')), findsOneWidget);
    expect(find.byKey(const Key('recorder-shutter')), findsNothing);

    await tester.tap(find.byKey(const Key('recorder-fallback')));
    await tester.pumpAndSettle();
    expect(popped, isNull); // null → caller opens the device file picker
  });

  testWidgets('record then stop returns the captured clip', (tester) async {
    final clip = PickedClip(
      bytes: Uint8List.fromList([1, 2, 3]),
      filename: 'recording.webm',
      mime: 'video/webm',
    );

    PickedClip? popped;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (ctx) => Scaffold(
          body: ElevatedButton(
            onPressed: () async {
              popped = await Navigator.of(ctx).push<PickedClip?>(MaterialPageRoute(
                builder: (_) => RecorderScreen(
                  controller: _FakeRecorder(available: true, result: clip),
                ),
              ));
            },
            child: const Text('go'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('go'));
    await tester.pumpAndSettle();

    // Live preview + shutter present.
    expect(find.byKey(const Key('recorder-shutter')), findsOneWidget);

    // Tap to start (a periodic timer runs → use pump, not pumpAndSettle).
    await tester.tap(find.byKey(const Key('recorder-shutter')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    // Tap to stop → screen pops the captured clip, now carrying the recorded duration (~1s)
    // so the editor can offer a trim window.
    await tester.tap(find.byKey(const Key('recorder-shutter')));
    await tester.pumpAndSettle();
    expect(popped, isNotNull);
    expect(popped!.bytes, same(clip.bytes));
    expect(popped!.filename, clip.filename);
    expect(popped!.mime, clip.mime);
    expect(popped!.durationS, 1.0);
  });
}

/// A const-constructible unavailable controller (so the screen can be `const`).
class _Unavailable implements RecorderController {
  const _Unavailable();
  @override
  Future<bool> initPreview({bool front = true}) async => false;
  @override
  Widget buildPreview() => const SizedBox.shrink();
  @override
  bool get canSwitchCamera => false;
  @override
  bool get isRecording => false;
  @override
  void startRecording() {}
  @override
  Future<PickedClip?> stopRecording() async => null;
  @override
  Future<bool> switchCamera() async => false;
  @override
  void dispose() {}
}
