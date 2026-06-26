/// Native (android/iOS/desktop/test) clip preview: write the clip's bytes to a temp file and
/// play it with `video_player`, with a tap-to-play overlay and a scrubbable progress bar.
///
/// Defensive: if the bytes can't be decoded (or there's no video plugin, e.g. the test VM),
/// it shows a film glyph instead of throwing, so the editor degrades gracefully.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../upload/clip_source_types.dart';

class ClipPreview extends StatefulWidget {
  const ClipPreview({super.key, required this.clip});

  final PickedClip clip;

  @override
  State<ClipPreview> createState() => _ClipPreviewState();
}

class _ClipPreviewState extends State<ClipPreview> {
  VideoPlayerController? _controller;
  Directory? _tmpDir;
  bool _failed = false;

  static const Map<String, String> _ext = {
    'video/mp4': 'mp4',
    'video/quicktime': 'mov',
    'video/webm': 'webm',
    'video/ogg': 'ogv',
  };

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    try {
      final dir = Directory.systemTemp.createTempSync('clip_preview');
      _tmpDir = dir;
      final ext = _ext[widget.clip.mime] ?? 'mp4';
      final file = File('${dir.path}/clip.$ext')..writeAsBytesSync(widget.clip.bytes);
      final c = VideoPlayerController.file(file);
      await c.initialize();
      if (!mounted) {
        await c.dispose();
        return;
      }
      await c.setLooping(true);
      _controller = c;
      setState(() {});
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  void _togglePlay() {
    final c = _controller;
    if (c == null || !c.value.isInitialized) return;
    setState(() => c.value.isPlaying ? c.pause() : c.play());
  }

  @override
  void dispose() {
    _controller?.dispose();
    try {
      _tmpDir?.deleteSync(recursive: true);
    } catch (_) {
      // best-effort temp cleanup
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = _controller;
    if (c == null || !c.value.isInitialized) return _glyph();
    return GestureDetector(
      key: const Key('clip-preview-surface'),
      onTap: _togglePlay,
      child: ColoredBox(
        color: Colors.black,
        child: Stack(
          fit: StackFit.expand,
          children: [
            Center(
              child: AspectRatio(
                aspectRatio: c.value.aspectRatio == 0 ? 16 / 9 : c.value.aspectRatio,
                child: VideoPlayer(c),
              ),
            ),
            // A play glyph while paused (tap anywhere to toggle).
            ValueListenableBuilder<VideoPlayerValue>(
              valueListenable: c,
              builder: (_, v, _) => v.isPlaying
                  ? const SizedBox.shrink()
                  : const Center(
                      child: Icon(Icons.play_circle_outline, color: Colors.white70, size: 56),
                    ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: VideoProgressIndicator(c, allowScrubbing: true),
            ),
          ],
        ),
      ),
    );
  }

  Widget _glyph() => ColoredBox(
        color: Colors.black,
        child: Center(
          child: Icon(
            _failed ? Icons.error_outline : Icons.movie_creation_outlined,
            color: Colors.white24,
            size: 56,
          ),
        ),
      );
}
