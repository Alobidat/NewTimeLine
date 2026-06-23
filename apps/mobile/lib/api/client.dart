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

  /// The current session JWT (ADR-0026), or null when anonymous. When present it is sent
  /// as `Authorization: Bearer <token>` on every request so writes resolve the real user;
  /// anonymous reads keep working when absent. Set by the auth state on sign-in / restore,
  /// cleared on sign-out and account deletion.
  String? sessionToken;

  /// Headers for an authenticated request: the optional Bearer plus any [extra].
  Map<String, String> _authHeaders([Map<String, String>? extra]) {
    return {
      if (sessionToken != null) 'authorization': 'Bearer $sessionToken',
      ...?extra,
    };
  }

  Future<dynamic> _getJson(String path, Map<String, String> query) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
    final resp = await _http.get(uri, headers: _authHeaders());
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
    final resp =
        await _http.post(uri, headers: _authHeaders(_jsonHeaders), body: jsonEncode(body));
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw ApiException('POST $uri → ${resp.statusCode}');
    }
    return resp.body.isEmpty ? null : jsonDecode(resp.body);
  }

  Future<dynamic> _patchJson(String path, Object body) async {
    final uri = Uri.parse('$baseUrl$path');
    final resp =
        await _http.patch(uri, headers: _authHeaders(_jsonHeaders), body: jsonEncode(body));
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw ApiException('PATCH $uri → ${resp.statusCode}');
    }
    return resp.body.isEmpty ? null : jsonDecode(resp.body);
  }

  Future<dynamic> _delete(String path, {Map<String, String>? query}) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
    final resp = await _http.delete(uri, headers: _authHeaders());
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

  // ── Feed / recommendations (social-and-feed §4, ADR-0028). The ranked video-first feed.

  /// One ranked page of [tab] (`GET /feed/{foryou|following|discover}`). [cursor] is the
  /// opaque token from the previous page (null for the first); [limit] caps the page size.
  /// Returns the decoded `{tab, items:[{event, hero_media_id, score}], next_cursor}` body —
  /// [FeedSource] maps it to the UI's `FeedItem`s (keeping this client layer feed-agnostic).
  Future<Map<String, dynamic>> feedPage(
    String tabSlug, {
    String? cursor,
    int limit = 20,
  }) async {
    return await _getJson('/feed/$tabSlug', {
      'cursor': ?cursor,
      'limit': limit.toString(),
    }) as Map<String, dynamic>;
  }

  // ── Social graph + promotion (social-and-feed §2). Promote/demote events, links, sources,
  // and actors; follow users/entities/events. All are interaction-gated (Bearer required).

  /// Follow a [targetType] (`user`|`entity`|`event`) by [targetId] (`POST /follow`).
  Future<void> follow(String targetType, String targetId) async {
    await _postJson('/follow', const {}, query: {
      'target_type': targetType,
      'target_id': targetId,
    });
  }

  /// Unfollow a [targetType] by [targetId] (`DELETE /follow`).
  Future<void> unfollow(String targetType, String targetId) async {
    await _delete('/follow', query: {
      'target_type': targetType,
      'target_id': targetId,
    });
  }

  /// Save an event to the caller's private collection (`POST /bookmark`, idempotent).
  Future<void> bookmark(String eventId) async {
    await _postJson('/bookmark', const {}, query: {'event_id': eventId});
  }

  /// Remove a saved event (`DELETE /bookmark`, idempotent).
  Future<void> unbookmark(String eventId) async {
    await _delete('/bookmark', query: {'event_id': eventId});
  }

  /// Whether the caller has [eventId] saved (`GET /bookmark/state`). False when anonymous.
  Future<bool> bookmarkState(String eventId) async {
    final j = await _getJson('/bookmark/state', {'event_id': eventId});
    if (j is Map) return (j['bookmarked'] as bool?) ?? false;
    return false;
  }

  /// The caller's saved events, newest-saved-first (`GET /me/bookmarks`). Requires a session.
  Future<List<EventRead>> myBookmarks({int limit = 50}) async {
    final list = await _getJson('/me/bookmarks', {'limit': limit.toString()}) as List;
    return list
        .map((e) => EventRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Whether the signed-in user follows [targetId] (`GET /follow/state`). False when anonymous.
  Future<bool> followState(String targetType, String targetId) async {
    final j = await _getJson('/follow/state', {
      'target_type': targetType,
      'target_id': targetId,
    });
    if (j is Map) return (j['following'] as bool?) ?? false;
    return false;
  }

  /// Follower/following counts for [targetType]/[targetId] (`GET /follow/counts`). When both
  /// are null the counts are for the signed-in user.
  Future<FollowCounts> followCounts({String? targetType, String? targetId}) async {
    return FollowCounts.fromJson(
      await _getJson('/follow/counts', {
        'target_type': ?targetType,
        'target_id': ?targetId,
      }) as Map<String, dynamic>,
    );
  }

  /// Promote (+1) / demote (-1) / clear (0) a [targetType]
  /// (`event`|`relation`|`source`|`entity`) by [targetId] (`POST /promote`). Returns the
  /// fresh `{mine, score, up, down}` tally.
  Future<PromoteResult> promote(
    String targetType,
    String targetId,
    int value,
  ) async {
    return PromoteResult.fromJson(
      await _postJson('/promote', {
        'target_type': targetType,
        'target_id': targetId,
        'value': value,
      }) as Map<String, dynamic>,
    );
  }

  /// The signed-in user's interest profile (`GET /me/interests`): weighted entities/
  /// categories/places the recommender learned from their activity.
  Future<InterestProfile> interests() async => InterestProfile.fromJson(
    await _getJson('/me/interests', const {}) as Map<String, dynamic>,
  );

  /// The signed-in user's uploaded events (`GET /account/uploads`). Best-effort: tolerates a
  /// list payload or a `{items|uploads|events:[…]}` envelope; callers degrade to "none yet".
  Future<List<EventRead>> myUploads({int limit = 50}) async {
    final j = await _getJson('/account/uploads', {'limit': limit.toString()});
    final list = (j is Map
            ? (j['items'] ?? j['uploads'] ?? j['events'])
            : j) as List? ??
        const [];
    return list
        .map((e) => EventRead.fromJson(
            (e is Map && e['event'] is Map ? e['event'] : e)
                as Map<String, dynamic>))
        .toList();
  }

  // ── Auth & account (Phase 4-G, ADR-0026). The login flow is OAuth2/OIDC auth-code+PKCE;
  // the backend mints a session JWT that [sessionToken] then attaches to every request.

  /// The sign-in options the backend offers (`GET /auth/providers`): the OAuth providers
  /// (config-driven, **may be empty**) plus whether the dev email-code login is available.
  /// The UI handles the empty/dev-only cases gracefully.
  Future<AuthOptions> authOptions() async => AuthOptions.fromJson(
    await _getJson('/auth/providers', const {}) as Map<String, dynamic>,
  );

  /// Begin dev email-code sign-in: email a one-time code to [email] (`POST /auth/dev/start`).
  /// In non-prod the code is echoed back ([devCode]) so the flow works without a live mailbox.
  Future<({bool sent, String? devCode})> devLoginStart(String email) async {
    final j = await _postJson('/auth/dev/start', {'email': email});
    final m = j as Map<String, dynamic>;
    return (sent: (m['sent'] as bool?) ?? false, devCode: m['dev_code'] as String?);
  }

  /// Complete dev email-code sign-in: exchange [email]+[code] for a session JWT
  /// (`POST /auth/dev/verify`). The returned session has no nested user — [AuthState.adopt]
  /// fills it via `/account/me`.
  Future<AuthSession> devLoginVerify(String email, String code) async {
    final j = await _postJson('/auth/dev/verify', {'email': email, 'code': code});
    return AuthSession.fromJson(j as Map<String, dynamic>);
  }

  /// Begin sign-in: the authorize URL + PKCE/state to round-trip (`GET /auth/{p}/login`).
  Future<LoginChallenge> loginChallenge(String provider, {String? redirectUri}) async {
    return LoginChallenge.fromJson(
      await _getJson('/auth/$provider/login', {'redirect_uri': ?redirectUri})
          as Map<String, dynamic>,
    );
  }

  /// Finish sign-in: exchange the provider [code]+[state] for a session JWT (+ user).
  /// Echoes the PKCE [codeVerifier] from the challenge when the backend expects it.
  Future<AuthSession> authCallback(
    String provider, {
    required String code,
    String? state,
    String? codeVerifier,
    String? redirectUri,
  }) async {
    final j = await _postJson('/auth/$provider/callback', {
      'code': code,
      'state': ?state,
      'code_verifier': ?codeVerifier,
      'redirect_uri': ?redirectUri,
    });
    return AuthSession.fromJson(j as Map<String, dynamic>);
  }

  /// The current versioned agreement to accept (`GET /auth/agreement`).
  Future<Agreement> agreement() async => Agreement.fromJson(
    await _getJson('/auth/agreement', const {}) as Map<String, dynamic>,
  );

  /// Whether the signed-in user has accepted the current version (`GET /auth/agreement/status`).
  Future<AgreementStatus> agreementStatus() async => AgreementStatus.fromJson(
    await _getJson('/auth/agreement/status', const {}) as Map<String, dynamic>,
  );

  /// Record acceptance of [version] (`POST /auth/agreement/accept`).
  Future<void> acceptAgreement(String version) async {
    await _postJson('/auth/agreement/accept', {'version': version});
  }

  /// Request an email-verification code be sent (`POST /auth/verify/request`).
  Future<void> requestEmailVerify({String? email}) async {
    await _postJson('/auth/verify/request', {'email': ?email});
  }

  /// Confirm email verification with the emailed [code] (`POST /auth/verify/confirm`).
  Future<void> confirmEmailVerify(String code) async {
    await _postJson('/auth/verify/confirm', {'code': code});
  }

  /// The signed-in user (`GET /account/me`). Requires a session.
  Future<SessionUser> me() async => SessionUser.fromJson(
    await _getJson('/account/me', const {}) as Map<String, dynamic>,
  );

  /// Absolute URL for the GDPR data export (`GET /account/export`) — a downloadable JSON
  /// archive of everything we hold about the user (ADR-0026). The Bearer is attached when
  /// fetched via [exportData]; this URL is for sharing/opening externally.
  String exportUrl() => '$baseUrl/account/export';

  /// Fetch the GDPR data export as a JSON string (`GET /account/export`).
  Future<String> exportData() async {
    final uri = Uri.parse('$baseUrl/account/export');
    final resp = await _http.get(uri, headers: _authHeaders());
    if (resp.statusCode != 200) {
      throw ApiException('GET $uri → ${resp.statusCode}');
    }
    return resp.body;
  }

  /// Irreversibly delete the account and all the user's data (`DELETE /account`, ADR-0026).
  Future<void> deleteAccount() async {
    await _delete('/account');
  }

  /// Absolute URL for a media item's bytes (streamed/redirected by the API).
  String mediaUrl(String mediaId) => '$baseUrl/media/$mediaId/raw';

  // ── User-generated video events (social-and-feed §3, ADR-0029). Write-gated; the server
  // returns 400 when the metadata-complete invariant (time/location/actors/link) is unmet.

  /// Upload a clip as a new event (`POST /upload`, multipart). Requires [title] + the
  /// metadata-complete fields: [tStart] (signed year), [geoLabel], at least one [actorNames]
  /// entry, and at least one [linkEventIds] target. The clip is supplied either as in-memory
  /// [fileBytes] (+ [filename]) or, when the platform can't read bytes, an external
  /// [sourceUrl]. Returns the decoded `{event, media, status}` response.
  Future<UploadResult> upload({
    required String title,
    required double tStart,
    double? tEnd,
    String timePrecision = 'day',
    required String geoLabel,
    required List<String> actorNames,
    required List<String> linkEventIds,
    List<int>? fileBytes,
    String? filename,
    String? sourceUrl,
  }) async {
    final uri = Uri.parse('$baseUrl/upload');
    final req = http.MultipartRequest('POST', uri)
      ..headers.addAll(_authHeaders())
      ..fields['title'] = title
      ..fields['t_start'] = tStart.toString()
      ..fields['t_end'] = (tEnd ?? tStart).toString()
      ..fields['time_precision'] = timePrecision
      ..fields['geo_label'] = geoLabel
      ..fields['actors'] = actorNames.join(',')
      ..fields['links'] = linkEventIds.join(',');
    if (sourceUrl != null && sourceUrl.isNotEmpty) {
      req.fields['source_url'] = sourceUrl;
    }
    if (fileBytes != null) {
      req.files.add(http.MultipartFile.fromBytes(
        'file',
        fileBytes,
        filename: filename ?? 'clip.mp4',
      ));
    }
    final streamed = await _http.send(req);
    final resp = await http.Response.fromStream(streamed);
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw ApiException('POST $uri → ${resp.statusCode}: ${resp.body}');
    }
    return UploadResult.fromJson(
      resp.body.isEmpty
          ? const {}
          : jsonDecode(resp.body) as Map<String, dynamic>,
    );
  }

  void close() => _http.close();
}
