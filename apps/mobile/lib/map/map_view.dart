/// The map surface: OSM tiles + event markers sized/coloured by severity, linked to the
/// shared time window. Tapping a marker opens the event detail sheet.
library;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../event/event_detail_sheet.dart';
import '../theme/severity.dart';
import 'geo.dart';
import 'map_model.dart';

class MapView extends StatefulWidget {
  const MapView({super.key, required this.model});

  final MapModel model;

  @override
  State<MapView> createState() => _MapViewState();
}

class _MapViewState extends State<MapView> {
  final MapController _map = MapController();

  void _syncBbox() {
    final b = _map.camera.visibleBounds;
    widget.model.setBbox(
      bboxString(west: b.west, south: b.south, east: b.east, north: b.north),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        FlutterMap(
          mapController: _map,
          options: MapOptions(
            initialCenter: const LatLng(20, 0),
            initialZoom: 1.6,
            onMapReady: _syncBbox,
            onPositionChanged: (camera, hasGesture) {
              if (hasGesture) _syncBbox();
            },
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.alobidat.chronos_app',
            ),
            AnimatedBuilder(
              animation: widget.model,
              builder: (context, _) => MarkerLayer(
                markers: [
                  for (final e in widget.model.events)
                    if (e.geo != null)
                      Marker(
                        point: LatLng(e.geo!.lat, e.geo!.lon),
                        width: 22,
                        height: 22,
                        child: _EventDot(
                          severity: e.severity,
                          onTap: () => showEventDetail(
                            context,
                            widget.model.fetchDetail(e.id),
                          ),
                        ),
                      ),
                ],
              ),
            ),
          ],
        ),
        // Loading + count chips.
        Positioned(
          right: 8,
          top: 8,
          child: AnimatedBuilder(
            animation: widget.model,
            builder: (context, _) => _MapBadge(
              loading: widget.model.loading,
              count: widget.model.events.length,
              error: widget.model.error,
            ),
          ),
        ),
        const Positioned(
          left: 8,
          bottom: 4,
          child: IgnorePointer(
            child: Text(
              '© OpenStreetMap contributors',
              style: TextStyle(fontSize: 10, color: Colors.white70),
            ),
          ),
        ),
      ],
    );
  }
}

class _EventDot extends StatelessWidget {
  const _EventDot({required this.severity, required this.onTap});
  final int severity;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = severityColor(severity);
    // Higher severity → larger dot.
    final size = 8.0 + (severity.clamp(0, 100) / 100.0) * 12.0;
    return GestureDetector(
      onTap: onTap,
      child: Center(
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.85),
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white, width: 1),
          ),
        ),
      ),
    );
  }
}

class _MapBadge extends StatelessWidget {
  const _MapBadge({required this.loading, required this.count, this.error});
  final bool loading;
  final int count;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = error != null ? 'map error' : '$count on map';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: scheme.surface.withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (loading)
            const SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          if (loading) const SizedBox(width: 6),
          Text(text, style: Theme.of(context).textTheme.labelMedium),
        ],
      ),
    );
  }
}
