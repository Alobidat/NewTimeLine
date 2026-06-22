/// Web implementation of [webVideoView]: a raw HTML `<video>` platform view that is ALSO the
/// feed's swipe surface.
///
/// We bypass `video_player` on the web because its platform view lays the `<video>` out at the
/// clip's natural aspect ratio (top-aligned → a strip), and Flutter's FittedBox/OverflowBox
/// can't restyle a platform view. Here we own the element, so `object-fit: cover` +
/// `width/height: 100%` gives a true full-bleed, TikTok-style crop. Muted + autoplay + loop +
/// playsinline reproduce the feed behaviour natively (no controller needed for a muted feed).
///
/// Crucially, a full-screen platform view is the **topmost DOM element** in its region on real
/// browsers, so it captures the pointer stream *before* Flutter's gesture layer ever sees it —
/// relying on `pointer-events: none` to let swipes fall through to a Flutter [GestureDetector]
/// is renderer-dependent and was silently eating every swipe over the clip. Instead we detect
/// the swipe in JS *on the element itself* (which is guaranteed to receive the touches) and
/// hand the result to the feed via [WebSwipe]. Off the web there is no `<video>` element, so the
/// feed's Flutter GestureDetector handles paging there.
library;

import 'dart:js_interop';
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;

/// A swipe gesture detected directly on the web `<video>` element: total travel ([dx], [dy])
/// and release velocity ([vx], [vy]) in logical px / px-per-second.
typedef WebSwipe = void Function(double dx, double dy, double vx, double vy);

// Register each (url) view factory at most once — re-registering a viewType throws.
final Set<String> _registered = <String>{};

// The current swipe handler per viewType, looked up *late* (at gesture time) so a clip revisited
// through its cached factory still routes to the live feed state, not a stale closure.
final Map<String, WebSwipe> _swipeHandlers = <String, WebSwipe>{};

Widget webVideoView(String url, {required bool muted, WebSwipe? onSwipe}) {
  // One viewType per url so swapping the feed's active clip rebuilds the element with a new src.
  final viewType = 'chronos-feed-video:$url';
  // Refresh the handler on every build (even when the factory is already registered) so it
  // always points at the current feed's navigation.
  if (onSwipe != null) {
    _swipeHandlers[viewType] = onSwipe;
  } else {
    _swipeHandlers.remove(viewType);
  }
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
      // This element IS the feed's swipe surface (see library doc). Keep it receiving pointer
      // input, but tell the browser not to treat drags as native scroll/zoom so our handlers see
      // the full gesture.
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
      _attachSwipe(v, viewType);
      return v;
    });
  }
  // The element styles itself to 100vw×100vh (above), so the platform-view host content-sizes
  // to the full screen — no Flutter-side sizing needed.
  return HtmlElementView(viewType: viewType);
}

/// Wire pointer-based swipe detection onto [v]. We track the press point and, on release,
/// classify the gesture (dominant axis, travel, velocity) and forward it to the live handler
/// for [viewType]. A tap (negligible travel) reports zero so the feed can ignore it. Mute-tap
/// is intentionally not handled here — the feed clip is muted by design.
void _attachSwipe(web.HTMLVideoElement v, String viewType) {
  var startX = 0.0, startY = 0.0, startT = 0.0;
  var tracking = false;

  final down = ((web.PointerEvent e) {
    tracking = true;
    startX = e.clientX.toDouble();
    startY = e.clientY.toDouble();
    startT = e.timeStamp.toDouble();
    // Capture so we still get the matching up even if the pointer leaves the element. Guarded:
    // an inactive pointer id throws NotFoundError, which would otherwise abort the handler.
    try {
      v.setPointerCapture(e.pointerId);
    } catch (_) {}
  }).toJS;

  final up = ((web.PointerEvent e) {
    if (!tracking) return;
    tracking = false;
    final dx = e.clientX.toDouble() - startX;
    final dy = e.clientY.toDouble() - startY;
    final dt = (e.timeStamp.toDouble() - startT) / 1000.0; // seconds
    final vx = dt > 0 ? dx / dt : 0.0;
    final vy = dt > 0 ? dy / dt : 0.0;
    _swipeHandlers[viewType]?.call(dx, dy, vx, vy);
  }).toJS;

  final cancel = ((web.PointerEvent _) {
    tracking = false;
  }).toJS;

  v.addEventListener('pointerdown', down);
  v.addEventListener('pointerup', up);
  v.addEventListener('pointercancel', cancel);
}
