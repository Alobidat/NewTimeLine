/// Thin HTTP client for the Chronos Event API.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import 'models.dart';

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => 'ApiException: $message';
}

class ApiClient {
  ApiClient({String? baseUrl, http.Client? client})
    : baseUrl = baseUrl ?? AppConfig.apiBaseUrl,
      _http = client ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<dynamic> _getJson(String path, Map<String, String> query) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
    final resp = await _http.get(uri);
    if (resp.statusCode != 200) {
      throw ApiException('GET $uri → ${resp.statusCode}');
    }
    return jsonDecode(resp.body);
  }

  /// Timeline window: events (sparse) or buckets (dense). Times are signed years.
  Future<TimelineResponse> timeline({
    required double t0,
    required double t1,
    String? bbox,
    int minSeverity = 0,
    int maxEvents = 500,
    int buckets = 200,
  }) async {
    final q = {
      't0': t0.toString(),
      't1': t1.toString(),
      'min_severity': minSeverity.toString(),
      'max_events': maxEvents.toString(),
      'buckets': buckets.toString(),
      'bbox': ?bbox,
    };
    return TimelineResponse.fromJson(
      await _getJson('/timeline', q) as Map<String, dynamic>,
    );
  }

  /// Geolocated events within a viewport bbox ("minLon,minLat,maxLon,maxLat").
  Future<List<EventRead>> map({
    required String bbox,
    double t0 = -5000000000,
    double t1 = 10000,
    int minSeverity = 0,
  }) async {
    final q = {
      'bbox': bbox,
      't0': t0.toString(),
      't1': t1.toString(),
      'min_severity': minSeverity.toString(),
    };
    final list = await _getJson('/map', q) as List;
    return list
        .map((e) => EventRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Full event detail incl. sources + sub-timeline references.
  Future<EventDetail> event(String id) async => EventDetail.fromJson(
    await _getJson('/events/$id', const {}) as Map<String, dynamic>,
  );

  void close() => _http.close();
}
