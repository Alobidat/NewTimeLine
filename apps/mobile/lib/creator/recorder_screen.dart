/// Full-screen in-app camera recorder UI (Creator Studio Phase 1). Shows a live preview, a
/// record/stop button with an elapsed timer, and a flip-camera control. On stop it returns the
/// captured [PickedClip] via `Navigator.pop`. If the camera is unavailable (no API / permission
/// denied), it shows a graceful message with a "Choose a file instead" fallback that pops null —
/// so the caller can use the device file picker, and the feature never dead-ends.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'recorder.dart';

/// Open the recorder and return the captured clip (or null if cancelled/unavailable).
Future<PickedClip?> recordClipInApp(BuildContext context) {
  return Navigator.of(context).push<PickedClip?>(
    MaterialPageRoute<PickedClip?>(
      fullscreenDialog: true,
      builder: (_) => RecorderScreen(controller: createRecorderController()),
    ),
  );
}

class RecorderScreen extends StatefulWidget {
  const RecorderScreen({super.key, required this.controller});

  final RecorderController controller;

  @override
  State<RecorderScreen> createState() => _RecorderScreenState();
}

class _RecorderScreenState extends State<RecorderScreen> {
  bool _initializing = true;
  bool _available = false;
  bool _recording = false;
  bool _finishing = false;
  Duration _elapsed = Duration.zero;
  Timer? _ticker;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final ok = await widget.controller.initPreview();
    if (!mounted) return;
    setState(() {
      _initializing = false;
      _available = ok;
    });
  }

  void _toggleRecord() {
    if (_recording) {
      _stop();
    } else {
      widget.controller.startRecording();
      _elapsed = Duration.zero;
      _ticker?.cancel();
      _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted) setState(() => _elapsed += const Duration(seconds: 1));
      });
      setState(() => _recording = true);
    }
  }

  Future<void> _stop() async {
    _ticker?.cancel();
    final recorded = _elapsed; // shutter-timer length → lets the editor offer a trim window
    setState(() {
      _recording = false;
      _finishing = true;
    });
    var clip = await widget.controller.stopRecording();
    if (clip != null && recorded > Duration.zero) {
      clip = clip.copyWith(durationS: recorded.inMilliseconds / 1000.0);
    }
    if (!mounted) return;
    Navigator.of(context).pop(clip);
  }

  Future<void> _flip() async {
    await widget.controller.switchCamera();
    if (mounted) setState(() {});
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  void dispose() {
    _ticker?.cancel();
    widget.controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: _initializing
            ? const Center(child: CircularProgressIndicator())
            : _available
                ? _recorderView()
                : _unavailableView(),
      ),
    );
  }

  Widget _unavailableView() => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.videocam_off_outlined, color: Colors.white54, size: 56),
              const SizedBox(height: 16),
              const Text(
                "Couldn't access the camera.\nCheck permissions, or pick a video file instead.",
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 20),
              FilledButton.tonal(
                key: const Key('recorder-fallback'),
                // Pop null → the caller (upload screen) opens the device file picker.
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Choose a file instead'),
              ),
            ],
          ),
        ),
      );

  Widget _recorderView() {
    return Stack(
      fit: StackFit.expand,
      children: [
        Positioned.fill(child: widget.controller.buildPreview()),
        // Top bar: close + elapsed timer.
        Positioned(
          top: 8,
          left: 8,
          right: 8,
          child: Row(
            children: [
              IconButton(
                key: const Key('recorder-close'),
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: _finishing ? null : () => Navigator.of(context).pop(),
              ),
              const Spacer(),
              if (_recording)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.fiber_manual_record, color: Colors.redAccent, size: 12),
                      const SizedBox(width: 6),
                      Text(_fmt(_elapsed),
                          style: const TextStyle(color: Colors.white, fontSize: 13)),
                    ],
                  ),
                ),
              const Spacer(),
              IconButton(
                key: const Key('recorder-flip'),
                icon: const Icon(Icons.cameraswitch_outlined, color: Colors.white),
                onPressed: (_recording || _finishing || !widget.controller.canSwitchCamera)
                    ? null
                    : _flip,
              ),
            ],
          ),
        ),
        // Record / stop button.
        Positioned(
          bottom: 32,
          left: 0,
          right: 0,
          child: Center(
            child: _finishing
                ? const CircularProgressIndicator(color: Colors.white)
                : GestureDetector(
                    key: const Key('recorder-shutter'),
                    onTap: _toggleRecord,
                    child: Container(
                      width: 76,
                      height: 76,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 4),
                      ),
                      child: Center(
                        child: Container(
                          width: _recording ? 30 : 60,
                          height: _recording ? 30 : 60,
                          decoration: BoxDecoration(
                            color: Colors.redAccent,
                            borderRadius:
                                BorderRadius.circular(_recording ? 6 : 30),
                          ),
                        ),
                      ),
                    ),
                  ),
          ),
        ),
      ],
    );
  }
}
