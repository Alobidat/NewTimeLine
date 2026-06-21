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

  static const _jsonHeaders = {'content-type': 'application/json'};

  /// POST [body] as JSON; accept any 2xx. Returns the decoded body (or null when empty).
  Future<dynamic> _postJson(
    String path,
    Object body, {
    Map<String, String>? query,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
    final resp = await _http.post(uri, headers: _jsonHeaders, body: jsonEncode(body));
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw ApiException('POST $uri → ${resp.statusCode}');
    }
    return resp.body.isEmpty ? null : jsonDecode(resp.body);
  }

  Future<dynamic> _patchJson(String path, Object body) async {
    final uri = Uri.parse('$baseUrl$path');
    final resp = await _http.patch(uri, headers: _jsonHeaders, body: jsonEncode(body));
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw ApiException('PATCH $uri → ${resp.statusCode}');
    }
    return resp.body.isEmpty ? null : jsonDecode(resp.body);
  }

  Future<dynamic> _delete(String path, {Map<String, String>? query}) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
    final resp = await _http.delete(uri);
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw ApiException('DELETE $uri → ${resp.statusCode}');
    }
    return resp.body.isEmpty ? null : jsonDecode(resp.body);
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

  /// Faceted search (events + actors + places) that also triggers live collection
  /// (ADR-0022). The response's `collecting` flag tells the UI to follow [searchStream]
  /// for results landing as the on-demand collector publishes them.
  Future<SearchResults> search({
    String? q,
    String? location,
    String? actor,
    double? t0,
    double? t1,
    int limit = 50,
    bool collect = true,
  }) async {
    return SearchResults.fromJson(
      await _getJson('/search', {
        'q': ?q,
        'location': ?location,
        'actor': ?actor,
        't0': ?t0?.toString(),
        't1': ?t1?.toString(),
        'limit': limit.toString(),
        'collect': collect.toString(),
      }) as Map<String, dynamic>,
    );
  }

  /// Server-Sent Events stream of *newly-collected* events matching a search subject
  /// (ADR-0022). Yields each fresh [EventRead] as the collector publishes it, so the
  /// search view can refresh live ("showing N results, collecting more…"). The stream
  /// ends when the server caps the connection or the subscription is cancelled.
  Stream<EventRead> searchStream({
    String? q,
    String? location,
    String? actor,
    double? t0,
    double? t1,
    int limit = 50,
  }) async* {
    final uri = Uri.parse('$baseUrl/search/stream').replace(
      queryParameters: {
        'q': ?q,
        'location': ?location,
        'actor': ?actor,
        't0': ?t0?.toString(),
        't1': ?t1?.toString(),
        'limit': limit.toString(),
      },
    );
    final req = http.Request('GET', uri)
      ..headers['Accept'] = 'text/event-stream';
    final resp = await _http.send(req);
    if (resp.statusCode != 200) {
      throw ApiException('GET $uri → ${resp.statusCode}');
    }
    // Parse the SSE frames line-by-line: accumulate `event:`/`data:` until a blank line.
    final lines = resp.stream.transform(utf8.decoder).transform(const LineSplitter());
    String? event;
    final data = StringBuffer();
    await for (final line in lines) {
      if (line.isEmpty) {
        // End of one frame: emit only `event` frames carrying a real EventRead.
        if (event == 'event' && data.isNotEmpty) {
          final json = jsonDecode(data.toString()) as Map<String, dynamic>;
          yield EventRead.fromJson(json);
        }
        event = null;
        data.clear();
        continue;
      }
      if (line.startsWith('event:')) {
        event = line.substring(6).trim();
      } else if (line.startsWith('data:')) {
        if (data.isNotEmpty) data.write('\n');
        data.write(line.substring(5).trim());
      }
    }
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

  // ── Interaction foundations (ADR-0025). Writes resolve a server-side actor stub; the
  // client never sends a user id (real OIDC sessions arrive in Phase 4 with no API change).

  /// Comments on an event, oldest-first (the article builds the reply tree client-side).
  Future<List<CommentRead>> comments(
    String eventId, {
    int limit = 200,
    int offset = 0,
  }) async {
    final list = await _getJson('/events/$eventId/comments', {
      'limit': limit.toString(),
      'offset': offset.toString(),
    }) as List;
    return list
        .map((e) => CommentRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Post a top-level comment ([parentId] null) or a reply. Returns the created comment.
  Future<CommentRead> addComment(
    String eventId,
    String body, {
    String? parentId,
  }) async {
    final j = await _postJson('/events/$eventId/comments', {
      'body': body,
      'parent_id': ?parentId,
    });
    return CommentRead.fromJson(j as Map<String, dynamic>);
  }

  /// Edit one's own comment body.
  Future<CommentRead> editComment(
    String eventId,
    String commentId,
    String body,
  ) async {
    final j = await _patchJson('/events/$eventId/comments/$commentId', {
      'body': body,
    });
    return CommentRead.fromJson(j as Map<String, dynamic>);
  }

  /// Soft-delete one's own comment (the server keeps it as `removed` so replies survive).
  Future<void> deleteComment(String eventId, String commentId) async {
    await _delete('/events/$eventId/comments/$commentId');
  }

  /// Aggregate reactions for an event (+ the actor's own set).
  Future<ReactionSummary> reactions(String eventId) async {
    return ReactionSummary.fromJson(
      await _getJson('/events/$eventId/reactions', const {})
          as Map<String, dynamic>,
    );
  }

  /// Toggle a reaction [kind] (like|dislike|important|doubt). Returns the fresh aggregate.
  Future<ReactionSummary> toggleReaction(String eventId, String kind) async {
    return ReactionSummary.fromToggle(
      await _postJson('/events/$eventId/reactions', {'kind': kind})
          as Map<String, dynamic>,
    );
  }

  /// Source-credibility vote tallies for an event (+ the actor's own verdicts).
  Future<SourceVotes> sourceVotes(String eventId) async {
    return SourceVotes.fromJson(
      await _getJson('/events/$eventId/source-votes', const {})
          as Map<String, dynamic>,
    );
  }

  /// Cast a source vote (verdict ∈ corroborate|dispute|irrelevant). Returns fresh tallies.
  Future<SourceVotes> castSourceVote(
    String eventId,
    String sourceId,
    String verdict,
  ) async {
    return SourceVotes.fromJson(
      await _postJson('/events/$eventId/source-votes', {
        'source_id': sourceId,
        'verdict': verdict,
      }) as Map<String, dynamic>,
    );
  }

  /// Assert a user link between two events (ADR-0025 §2.4). Default kind `thematic`.
  Future<void> createLink(
    String srcEvent,
    String dstEvent, {
    String kind = 'thematic',
  }) async {
    await _postJson('/links', {
      'src_event': srcEvent,
      'dst_event': dstEvent,
      'kind': kind,
    });
  }

  /// Remove a previously-asserted user link.
  Future<void> removeLink(
    String srcEvent,
    String dstEvent, {
    String kind = 'thematic',
  }) async {
    await _delete('/links', query: {
      'src_event': srcEvent,
      'dst_event': dstEvent,
      'kind': kind,
    });
  }

  // ── Social graph + promotion (social-and-feed §2, Phase 4-B). These endpoints are NOT
  // live yet — the backend builds them in a parallel wave. The feed shell calls them and
  // tolerates failure gracefully (the UI shows a snackbar). The signatures match the
  // documented contract so wiring is a no-op once the routes exist.

  /// Follow a user/entity (social-and-feed §2). TODO(phase-4-B): backend route lands later;
  /// throws [ApiException] until then (callers catch + snackbar).
  Future<void> followAuthor(String authorId) async {
    await _postJson('/follows', {'target_id': authorId, 'target_kind': 'user'});
  }

  /// Promote (up) or demote (down) an event (social-and-feed §2). TODO(phase-4-B): until the
  /// dedicated promote route lands, the feed maps this to the live reaction substrate
  /// ([toggleReaction]); this method targets the future endpoint.
  Future<void> promoteEvent(String eventId, {required bool up}) async {
    await _postJson('/events/$eventId/promote', {'direction': up ? 'up' : 'down'});
  }

  /// Absolute URL for a media item's bytes (streamed/redirected by the API).
  String mediaUrl(String mediaId) => '$baseUrl/media/$mediaId/raw';

  void close() => _http.close();
}
