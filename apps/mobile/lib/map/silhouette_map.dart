/// The abstract, basemap-free map: a gradient void on which only the *involved* countries
/// are drawn as glowing silhouettes, with event pins in their true locations. No street
/// tiles — the focus is purely "where in the world is this story happening".
///
/// Drawing + which countries to show is driven entirely by the parent (it knows the current
/// summary / selection); this widget just renders and reports camera moves.
library;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../theme/severity.dart';
import 'country_atlas.dart';

/// One event pin to plot.
class MapPin {
  const MapPin({
    required this.id,
    required this.point,
    required this.severity,
    required this.onTap,
    this.label,
    this.selected = false,
  });

  final String id;
  final LatLng point;
  final int severity;
  final VoidCallback onTap;
  final String? label;
  final bool selected;
}

class SilhouetteMap extends StatelessWidget {
  const SilhouetteMap({
    super.key,
    required this.controller,
    required this.countries,
    required this.pins,
    this.countryWeights = const {},
    this.onMapReady,
    this.onCameraMove,
  });

  final MapController controller;

  /// The countries to draw (others are simply omitted — that's the whole aesthetic).
  final List<Country> countries;

  /// Event pins to plot on top.
  final List<MapPin> pins;

  /// country.id → event count, used to scale each silhouette's glow.
  final Map<String, int> countryWeights;

  final VoidCallback? onMapReady;

  /// Called when the user pans/zooms (so the parent can refilter by viewport bbox).
  final void Function(LatLngBounds visibleBounds)? onCameraMove;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final maxWeight = countryWeights.values.fold<int>(1, (m, v) => v > m ? v : m);

    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            const Color(0xFF0A0E1A),
            scheme.surface,
            const Color(0xFF0A0E1A),
          ],
        ),
      ),
      child: FlutterMap(
        mapController: controller,
        options: MapOptions(
          initialCenter: const LatLng(20, 0),
          initialZoom: 1.6,
          minZoom: 1.0,
          maxZoom: 12,
          backgroundColor: Colors.transparent,
          cameraConstraint: CameraConstraint.contain(
            bounds: LatLngBounds(const LatLng(-85, -180), const LatLng(85, 180)),
          ),
          onMapReady: onMapReady,
          onPositionChanged: (camera, hasGesture) {
            if (hasGesture) onCameraMove?.call(camera.visibleBounds);
          },
        ),
        children: [
          PolygonLayer(polygons: _polygons(scheme, maxWeight)),
          MarkerLayer(markers: [for (final p in pins) _pinMarker(context, p)]),
        ],
      ),
    );
  }

  List<Polygon> _polygons(ColorScheme scheme, int maxWeight) {
    final out = <Polygon>[];
    for (final c in countries) {
      final w = (countryWeights[c.id] ?? 1) / maxWeight; // 0..1
      final fill = scheme.primary.withValues(alpha: 0.10 + 0.30 * w);
      final border = scheme.primary.withValues(alpha: 0.55 + 0.35 * w);
      for (final ring in c.polygons) {
        out.add(
          Polygon(
            points: ring.outer,
            holePointsList: ring.holes.isEmpty ? null : ring.holes,
            color: fill,
            borderColor: border,
            borderStrokeWidth: 1.2,
          ),
        );
      }
    }
    return out;
  }

  Marker _pinMarker(BuildContext context, MapPin p) {
    return Marker(
      point: p.point,
      width: 140,
      height: 54,
      alignment: Alignment.topCenter,
      child: _Pin(pin: p),
    );
  }
}

class _Pin extends StatelessWidget {
  const _Pin({required this.pin});
  final MapPin pin;

  @override
  Widget build(BuildContext context) {
    final color = severityColor(pin.severity);
    final size = pin.selected ? 22.0 : 10.0 + (pin.severity.clamp(0, 100) / 100.0) * 10.0;
    return GestureDetector(
      onTap: pin.onTap,
      behavior: HitTestBehavior.opaque,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 250),
            width: size,
            height: size,
            decoration: BoxDecoration(
              color: color.withValues(alpha: pin.selected ? 1 : 0.85),
              shape: BoxShape.circle,
              border: Border.all(
                color: Colors.white,
                width: pin.selected ? 2.5 : 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: color.withValues(alpha: pin.selected ? 0.9 : 0.5),
                  blurRadius: pin.selected ? 18 : 8,
                  spreadRadius: pin.selected ? 2 : 0,
                ),
              ],
            ),
          ),
          if (pin.label != null)
            Container(
              margin: const EdgeInsets.only(top: 3),
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.45),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                pin.label!,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 10, color: Colors.white),
              ),
            ),
        ],
      ),
    );
  }
}
