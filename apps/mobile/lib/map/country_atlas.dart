/// Loads the bundled simplified world-countries GeoJSON once and answers two questions
/// the silhouette map needs: which country contains a point (point-in-polygon), and what
/// rings to draw for a country. Events only carry a lat/lon + free-text geo_label, so we
/// derive the *involved countries* by locating each event point in this atlas.
library;

import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:latlong2/latlong.dart';

const _assetPath = 'assets/geo/countries.simplified.geojson';

/// One polygon of a country: an outer ring plus any holes (for drawing + hit-testing).
class CountryRing {
  CountryRing(this.outer, this.holes);
  final List<LatLng> outer;
  final List<List<LatLng>> holes;
}

/// A country silhouette: name/iso + its polygons, with a cached bbox for fast rejection.
class Country {
  Country({
    required this.name,
    required this.iso,
    required this.polygons,
    required this.minLat,
    required this.minLon,
    required this.maxLat,
    required this.maxLon,
  });

  final String name;
  final String? iso;
  final List<CountryRing> polygons;
  final double minLat, minLon, maxLat, maxLon;

  String get id => iso ?? name;

  bool contains(LatLng p) {
    if (p.latitude < minLat ||
        p.latitude > maxLat ||
        p.longitude < minLon ||
        p.longitude > maxLon) {
      return false;
    }
    for (final ring in polygons) {
      if (_inRing(p, ring.outer) && !ring.holes.any((h) => _inRing(p, h))) {
        return true;
      }
    }
    return false;
  }

  /// Ray-casting point-in-polygon on (lon=x, lat=y).
  static bool _inRing(LatLng p, List<LatLng> ring) {
    var inside = false;
    final x = p.longitude, y = p.latitude;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      final xi = ring[i].longitude, yi = ring[i].latitude;
      final xj = ring[j].longitude, yj = ring[j].latitude;
      final intersects =
          ((yi > y) != (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
      if (intersects) inside = !inside;
    }
    return inside;
  }
}

class CountryAtlas {
  CountryAtlas(this._countries);
  final List<Country> _countries;

  List<Country> get countries => _countries;
  bool get isEmpty => _countries.isEmpty;

  /// Parse the bundled GeoJSON once. Returns an empty atlas (never throws) if the asset is
  /// missing/corrupt — the map then simply shows markers without silhouettes.
  static Future<CountryAtlas> load() async {
    try {
      final raw = await rootBundle.loadString(_assetPath);
      final json = jsonDecode(raw) as Map<String, dynamic>;
      final features = (json['features'] as List?) ?? const [];
      return CountryAtlas(
        features
            .map((f) => _parseFeature(f as Map<String, dynamic>))
            .whereType<Country>()
            .toList(),
      );
    } catch (_) {
      return CountryAtlas(const []);
    }
  }

  /// The country containing [p], or null (ocean / outside all polygons).
  Country? countryAt(LatLng p) {
    for (final c in _countries) {
      if (c.contains(p)) return c;
    }
    return null;
  }

  /// The country containing [p]; if the point falls in ocean / outside every polygon, the
  /// nearest country by bbox-centroid distance (so a coastal or disputed point still lights
  /// up a country). Returns null only for an empty atlas. Part of the ADR-0020 fallback.
  Country? countryAtOrNearest(LatLng p) {
    final hit = countryAt(p);
    if (hit != null) return hit;
    Country? best;
    var bestD = double.infinity;
    for (final c in _countries) {
      final cy = (c.minLat + c.maxLat) / 2, cx = (c.minLon + c.maxLon) / 2;
      final dy = cy - p.latitude, dx = cx - p.longitude;
      final d = dy * dy + dx * dx;
      if (d < bestD) {
        bestD = d;
        best = c;
      }
    }
    return best;
  }

  /// Resolve a free-text place label (e.g. "United Kingdom", "GBR", "Iran") to a country by
  /// matching its name or ISO, case-insensitively. Returns null if no match. Lets an event
  /// with a geo_label but no usable coordinate still highlight a country.
  Country? countryByName(String? label) {
    if (label == null) return null;
    final q = label.trim().toLowerCase();
    if (q.isEmpty) return null;
    for (final c in _countries) {
      if (c.name.toLowerCase() == q || (c.iso?.toLowerCase() == q)) return c;
    }
    // Loose contains match (e.g. label "Tehran, Iran" → "Iran").
    for (final c in _countries) {
      final n = c.name.toLowerCase();
      if (n.length > 3 && q.contains(n)) return c;
    }
    return null;
  }

  /// The distinct countries touched by any of [points] (nulls ignored), in first-seen order.
  List<Country> resolve(Iterable<LatLng?> points) {
    final seen = <String>{};
    final out = <Country>[];
    for (final p in points) {
      if (p == null) continue;
      final c = countryAt(p);
      if (c != null && seen.add(c.id)) out.add(c);
    }
    return out;
  }

  Country? byId(String id) {
    for (final c in _countries) {
      if (c.id == id) return c;
    }
    return null;
  }

  static Country? _parseFeature(Map<String, dynamic> f) {
    final props = (f['properties'] as Map<String, dynamic>?) ?? const {};
    final geom = f['geometry'] as Map<String, dynamic>?;
    if (geom == null) return null;
    final type = geom['type'] as String?;
    final coords = geom['coordinates'] as List?;
    if (coords == null) return null;

    final polygons = <CountryRing>[];
    if (type == 'Polygon') {
      polygons.add(_ringSet(coords));
    } else if (type == 'MultiPolygon') {
      for (final poly in coords) {
        polygons.add(_ringSet(poly as List));
      }
    } else {
      return null;
    }
    if (polygons.isEmpty) return null;

    var minLat = 90.0, minLon = 180.0, maxLat = -90.0, maxLon = -180.0;
    for (final ring in polygons) {
      for (final pt in ring.outer) {
        minLat = pt.latitude < minLat ? pt.latitude : minLat;
        maxLat = pt.latitude > maxLat ? pt.latitude : maxLat;
        minLon = pt.longitude < minLon ? pt.longitude : minLon;
        maxLon = pt.longitude > maxLon ? pt.longitude : maxLon;
      }
    }

    return Country(
      name: (props['name'] as String?) ?? 'Unknown',
      iso: props['iso'] as String?,
      polygons: polygons,
      minLat: minLat,
      minLon: minLon,
      maxLat: maxLat,
      maxLon: maxLon,
    );
  }

  /// A GeoJSON Polygon coordinate array → outer ring + holes (each as LatLng list).
  static CountryRing _ringSet(List rings) {
    final converted = rings.map(_ring).toList();
    return CountryRing(
      converted.isEmpty ? const [] : converted.first,
      converted.length > 1 ? converted.sublist(1) : const [],
    );
  }

  static List<LatLng> _ring(dynamic ring) => (ring as List)
      .map((c) => LatLng(
            ((c as List)[1] as num).toDouble(),
            (c[0] as num).toDouble(),
          ))
      .toList();
}
