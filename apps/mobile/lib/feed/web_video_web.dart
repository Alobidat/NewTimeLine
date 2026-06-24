/// Web implementation of [webVideoView]: a raw, **decorative** full-bleed HTML `<video>`.
///
/// We bypass `video_player` on the web because its platform view lays the `<video>` out at the
/// clip's natural aspect ratio (top-aligned → a strip), and Flutter's FittedBox/OverflowBox
/// can't restyle a platform view. Here we own the element, so `object-fit: contain` +
/// `width/height: 100vw/100vh` scales the whole clip to fit the viewport with every edge visible
/// ("best mode"), letterboxing onto black. Muted + autoplay + loop + playsinline reproduce the
/// feed behaviour natively (no controller needed for a muted feed).
///
/// The clip is purely visual: it is set `pointer-events: none` so it NEVER captures the pointer
/// stream — every swipe/tap falls straight through to Flutter's gesture layer, which owns all
/// feed navigation. (Relying on the engine's default pointer-events for a platform view was
/// renderer-/device-dependent: on some real browsers the `<video>` stayed hit-testable and
/// swallowed swipes over its centre while the edges — painted Flutter overlays — still worked.
/// Setting it explicitly makes the behaviour deterministic everywhere.)
library;

import 'dart:js_interop';
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;

// Register each (url) view factory at most once — re-registering a viewType throws.
final Set<String> _registered = <String>{};

/// Feed-wide mute state for the web `<video>` clips. Starts **muted** because browsers only
/// allow autoplay without a user gesture when muted. A tap on the feed's volume button flips
/// it via [setFeedMuted]; every live clip and any clip created afterwards follows. Exposed as
/// a [ValueNotifier] so the volume button can rebuild its icon.
final ValueNotifier<bool> feedMuted = ValueNotifier<bool>(true);

// Every live feed <video>, so [setFeedMuted] can update them all at once. Disconnected
// elements are pruned lazily (an HtmlElementView gives no dispose hook for the element).
final Set<web.HTMLVideoElement> _live = <web.HTMLVideoElement>{};

/// Mute/unmute the whole feed. Toggling to unmuted counts as the user gesture that lets the
/// browser play audio, so any paused clip is nudged back into playback.
void setFeedMuted(bool muted) {
  feedMuted.value = muted;
  _live.removeWhere((v) => !v.isConnected);
  for (final v in _live) {
    v.muted = muted;
    v.defaultMuted = muted;
    if (!muted && v.paused) v.play();
  }
}

Widget webVideoView(String url, {required bool muted}) {
  // One viewType per url so swapping the feed's active clip rebuilds the element with a new src.
  final viewType = 'chronos-feed-video:$url';
  if (_registered.add(viewType)) {
    ui_web.platformViewRegistry.registerViewFactory(viewType, (int _) {
      final v = web.HTMLVideoElement();
      // Inherit the feed-wide mute preference (not the call-site arg): once the user has
      // unmuted, clips they swipe to should keep playing with sound. Set BEFORE src/play so
      // the browser's muted-autoplay allowance still applies on the muted (default) path.
      v.muted = feedMuted.value;
      v.defaultMuted = feedMuted.value;
      _live.removeWhere((e) => !e.isConnected);
      _live.add(v);
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
      // "Best mode": contain — the whole clip is always visible at its true aspect ratio, scaled
      // to fit the viewport, never cropping an edge. A portrait/landscape clip letterboxes onto
      // the black backdrop rather than being zoomed-in and cut off.
      v.style.setProperty('object-fit', 'contain');
      v.style.setProperty('background-color', 'black');
      // Decorative only — let every pointer/touch fall through to Flutter's gesture layer so the
      // feed's GestureDetector handles swipes uniformly over the whole screen (centre included).
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
