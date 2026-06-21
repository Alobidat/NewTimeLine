/// Web implementation of [webVideoView]: a raw HTML `<video>` platform view.
///
/// We bypass `video_player` on the web because its platform view lays the `<video>` out at the
/// clip's natural aspect ratio (top-aligned → a strip), and Flutter's FittedBox/OverflowBox
/// can't restyle a platform view. Here we own the element, so `object-fit: cover` +
/// `width/height: 100%` gives a true full-bleed, TikTok-style crop. Muted + autoplay + loop +
/// playsinline reproduce the feed behaviour natively (no controller needed for a muted feed).
library;

import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;

// Register each (url) view factory at most once — re-registering a viewType throws.
final Set<String> _registered = <String>{};

Widget webVideoView(String url, {required bool muted}) {
  // One viewType per url so swapping the feed's active clip rebuilds the element with a new src.
  final viewType = 'chronos-feed-video:$url';
  if (_registered.add(viewType)) {
    ui_web.platformViewRegistry.registerViewFactory(viewType, (int _) {
      final v = web.HTMLVideoElement();
      v.src = url;
      v.autoplay = true;
      v.loop = true;
      v.muted = muted;
      v.defaultMuted = muted;
      v.controls = false;
      // playsInline keeps mobile Safari/Chrome from going fullscreen on autoplay.
      v.setAttribute('playsinline', 'true');
      v.setAttribute('webkit-playsinline', 'true');
      v.preload = 'auto';
      v.style.setProperty('width', '100%');
      v.style.setProperty('height', '100%');
      v.style.setProperty('object-fit', 'cover');
      v.style.setProperty('background-color', 'black');
      // Autoplay can be deferred by the browser; kick it (ignore the promise rejection).
      v.play();
      return v;
    });
  }
  return HtmlElementView(viewType: viewType);
}
