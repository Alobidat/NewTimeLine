/// Tween-animates the flutter_map camera (center + zoom) so selecting an event, hopping to
/// a related event, or fitting all involved countries *glides* instead of cutting. Hand-
/// rolled on top of [MapController] + an [AnimationController] to avoid a new dependency.
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

class AnimatedMapController {
  AnimatedMapController({required TickerProvider vsync})
    : _anim = AnimationController(vsync: vsync) {
    _anim.addListener(_tick);
  }

  /// Pass this to [FlutterMap.mapController].
  final MapController mapController = MapController();
  final AnimationController _anim;

  LatLng _fromCenter = const LatLng(20, 0);
  LatLng _toCenter = const LatLng(20, 0);
  double _fromZoom = 1.6;
  double _toZoom = 1.6;
  static const _curve = Curves.easeInOutCubic;

  void _tick() {
    final t = _curve.transform(_anim.value);
    final center = LatLng(
      _fromCenter.latitude + (_toCenter.latitude - _fromCenter.latitude) * t,
      _fromCenter.longitude + (_toCenter.longitude - _fromCenter.longitude) * t,
    );
    final zoom = _fromZoom + (_toZoom - _fromZoom) * t;
    mapController.move(center, zoom);
  }

  /// Glide the camera to [dest] at [zoom].
  void animateTo(
    LatLng dest,
    double zoom, {
    Duration duration = const Duration(milliseconds: 900),
  }) {
    final cam = mapController.camera;
    _fromCenter = cam.center;
    _fromZoom = cam.zoom;
    _toCenter = dest;
    _toZoom = zoom;
    _anim
      ..duration = duration
      ..forward(from: 0);
  }

  /// Glide to frame all of [points] (e.g. every involved country's extent).
  void animateFit(
    List<LatLng> points, {
    EdgeInsets padding = const EdgeInsets.all(48),
    double maxZoom = 6,
    Duration duration = const Duration(milliseconds: 900),
  }) {
    if (points.isEmpty) return;
    final bounds = LatLngBounds.fromPoints(points);
    final fit = CameraFit.bounds(bounds: bounds, padding: padding)
        .fit(mapController.camera);
    animateTo(
      fit.center,
      fit.zoom > maxZoom ? maxZoom : fit.zoom,
      duration: duration,
    );
  }

  void dispose() {
    _anim
      ..removeListener(_tick)
      ..dispose();
  }
}
