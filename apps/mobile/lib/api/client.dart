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

  /// Bandwidth-safe distillation of a timeframe (+ optional bbox): heat buckets, top
  /// entities/places, and a capped set of representative events for a montage. Payload
  /// stays bounded no matter how many events match — the semantic-zoom "summary".
  Future<TimelineSummary> timelineSummary({
    required double t0,
    required double t1,
    String? bbox,
    int minSeverity = 0,
  }) async {
    final q = {
      't0': t0.toString(),
      't1': t1.toString(),
      'min_severity': minSeverity.toString(),
      'bbox': ?bbox,
    };
    return TimelineSummary.fromJson(
      await _getJson('/timeline/summary', q) as Map<String, dynamic>,
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

  /// Full event detail incl. sources, sub-timeline references, entities, and media.
  Future<EventDetail> event(String id) async => EventDetail.fromJson(
    await _getJson('/events/$id', const {}) as Map<String, dynamic>,
  );

  /// Search events by free text (title or linked entity name) + optional year range.
  Future<List<EventRead>> search({String? q, double? t0, double? t1, int limit = 50}) async {
    final list = await _getJson('/search', {
      'q': ?q,
      't0': ?t0?.toString(),
      't1': ?t1?.toString(),
      'limit': limit.toString(),
    }) as List;
    return list.map((e) => EventRead.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// Entity lookup by name (busiest first).
  Future<List<EntityRead>> entities({String? q, String? kind, int limit = 30}) async {
    final list = await _getJson('/entities', {
      'q': ?q,
      'kind': ?kind,
      'limit': limit.toString(),
    }) as List;
    return list.map((e) => EntityRead.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// Events linking ALL given entities (e.g. US + Iran), time-ordered.
  Future<List<EventRead>> eventsByEntities(List<String> ids, {int limit = 200}) async {
    final list = await _getJson('/events/by-entities', {
      'ids': ids.join(','),
      'limit': limit.toString(),
    }) as List;
    return list.map((e) => EventRead.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// One-hop related events across all relation kinds.
  Future<List<RelatedEvent>> related(String id, {String direction = 'both'}) async {
    final list = await _getJson('/events/$id/related', {'direction': direction}) as List;
    return list.map((e) => RelatedEvent.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// The causal chain around an event (back = led to it, forward = it caused).
  Future<ChainResponse> chain(String id, {String direction = 'both', int depth = 3}) async {
    return ChainResponse.fromJson(
      await _getJson('/events/$id/chain', {'direction': direction, 'depth': depth.toString()})
          as Map<String, dynamic>,
    );
  }

  /// Absolute URL for a media item's bytes (streamed/redirected by the API).
  String mediaUrl(String mediaId) => '$baseUrl/media/$mediaId/raw';

  void close() => _http.close();
}
