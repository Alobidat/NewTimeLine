/// Web clip preview: a blob-URL HTML `<video controls>` so the user can play/scrub the chosen
/// clip in the editor before publishing. We own the element (like [web_video_web.dart]) so it
/// fits the box with `object-fit: contain`; native controls give play/pause + seek for free.
///
/// The object URL is created from the in-memory bytes and **revoked on dispose** so the blob
/// doesn't leak. Falls back to a film glyph if the blob URL can't be made.
library;

import 'dart:js_interop';
import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

import '../upload/clip_source_types.dart';

// A viewType is registered at most once per object URL (re-registering a viewType throws).
final Set<String> _registered = <String>{};

class ClipPreview extends StatefulWidget {
  const ClipPreview({super.key, required this.clip});

  final PickedClip clip;

  @override
  State<ClipPreview> createState() => _ClipPreviewState();
}

class _ClipPreviewState extends State<ClipPreview> {
  String? _url;
  String? _viewType;

  @override
  void initState() {
    super.initState();
    try {
      final blob = web.Blob(
        [widget.clip.bytes.toJS].toJS,
        web.BlobPropertyBag(type: widget.clip.mime),
      );
      final url = web.URL.createObjectURL(blob);
      _url = url;
      final viewType = 'chronos-clip-preview:$url';
      _viewType = viewType;
      if (_registered.add(viewType)) {
        ui_web.platformViewRegistry.registerViewFactory(viewType, (int _) {
          final v = web.HTMLVideoElement()
            ..src = url
            ..controls = true
            ..setAttribute('playsinline', 'true');
          v.style
            ..width = '100%'
            ..height = '100%'
            ..objectFit = 'contain'
            ..background = 'black';
          return v;
        });
      }
    } catch (_) {
      _url = null; // blob creation failed → glyph fallback
    }
  }

  @override
  void dispose() {
    final url = _url;
    if (url != null) web.URL.revokeObjectURL(url);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final viewType = _viewType;
    if (viewType == null) {
      return const ColoredBox(
        color: Colors.black,
        child: Center(
          child: Icon(Icons.movie_creation_outlined, color: Colors.white24, size: 56),
        ),
      );
    }
    return HtmlElementView(viewType: viewType);
  }
}
