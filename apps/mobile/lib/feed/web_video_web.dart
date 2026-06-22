/// Web implementation of [webVideoView]: a raw HTML `<video>` platform view.
///
/// We bypass `video_player` on the web because its platform view lays the `<video>` out at the
/// clip's natural aspect ratio (top-aligned → a strip), and Flutter's FittedBox/OverflowBox
/// can't restyle a platform view. Here we own the element, so `object-fit: cover` +
/// `width/height: 100%` gives a true full-bleed, TikTok-style crop. Muted + autoplay + loop +
/// playsinline reproduce the feed behaviour natively (no controller needed for a muted feed).
library;

import 'dart:js_interop';
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
      // Mute BEFORE src/play so the browser's muted-autoplay allowance applies.
      v.muted = muted;
      v.defaultMuted = muted;
      v.autoplay = true;
      v.loop = true;
      v.controls = false;
      v.src = url;
      // playsInline keeps mobile Safari/Chrome from going fullscreen on autoplay.
      v.setAttribute('playsinline', 'true');
      v.setAttribute('webkit-playsinline', 'true');
      v.preload = 'auto';
      // The platform-view host is content-sized (height:auto), so a height:100% video collapses
      // it to a strip. Give the element an explicit viewport-unit size in normal flow: the host
      // grows to the full screen, so Flutter composites the clip full-bleed below the overlays.
      v.style.setProperty('display', 'block');
      v.style.setProperty('width', '100vw');
      v.style.setProperty('height', '100vh');
      v.style.setProperty('object-fit', 'cover');
      v.style.setProperty('background-color', 'black');
      // The feed clip is decorative (muted autoplay, no controls). Make it ignore pointer +
      // touch input so swipes/taps fall through to Flutter's gesture layer — otherwise this
      // full-screen <video> element captures every touch and the vertical feed can't be paged.
      v.style.setProperty('pointer-events', 'none');
      v.style.setProperty('touch-action', 'none');
      // Robust autoplay: a play() before the element is attached rejects, and the `autoplay`
      // attribute isn't always honored for a dynamically-created element. So (re)start playback
      // whenever the media becomes ready — muted playback is allowed without a user gesture.
      // Promise rejections are ignored (toDart not awaited).
      final kick = ((web.Event _) {
        if (v.paused) v.play();
      }).toJS;
      v.addEventListener('loadeddata', kick);
      v.addEventListener('canplay', kick);
      v.play();
      return v;
    });
  }
  // The element styles itself to 100vw×100vh (above), so the platform-view host content-sizes
  // to the full screen — no Flutter-side sizing needed.
  return HtmlElementView(viewType: viewType);
}
