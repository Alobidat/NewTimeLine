/// Dart models mirroring the Chronos Event API DTOs (chronos_core.schemas).
/// Only fields the client uses are included.
library;

import '../domain/time_format.dart';

double _d(Object? v) => (v as num).toDouble();

class GeoPoint {
  const GeoPoint(this.lon, this.lat);
  final double lon;
  final double lat;

  static GeoPoint? fromJson(Map<String, dynamic>? j) =>
      j == null ? null : GeoPoint(_d(j['lon']), _d(j['lat']));
}

class EventRead {
  EventRead({
    required this.id,
    required this.title,
    required this.tStart,
    required this.tEnd,
    required this.precision,
    required this.severity,
    required this.confidence,
    required this.sourceCount,
    this.summary,
    this.instant,
    this.category,
    this.geo,
    this.geoLabel,
    this.tags = const [],
    this.authorId,
  });

  final String id;
  final String title;
  final String? summary;
  final double tStart;
  final double tEnd;
  final TimePrecision precision;
  final DateTime? instant;
  final String? category;
  final List<String> tags;
  final int severity;
  final int confidence;
  final int sourceCount;
  final GeoPoint? geo;
  final String? geoLabel;

  /// The uploading user's id for user-generated clips (origin_kind='user'); null for
  /// agent/seed events. Drives the feed's "follow the creator" affordance.
  final String? authorId;

  static DateTime? _dt(Object? v) =>
      v == null ? null : DateTime.tryParse(v as String);

  factory EventRead.fromJson(Map<String, dynamic> j) => EventRead(
    id: j['id'] as String,
    title: j['title'] as String,
    summary: j['summary'] as String?,
    tStart: _d(j['t_start']),
    tEnd: _d(j['t_end']),
    precision: TimePrecision.parse(j['time_precision'] as String),
    instant: _dt(j['instant']),
    category: j['category'] as String?,
    tags: (j['tags'] as List?)?.cast<String>() ?? const [],
    severity: j['severity'] as int,
    confidence: j['confidence'] as int,
    sourceCount: j['source_count'] as int,
    geo: GeoPoint.fromJson(j['geo'] as Map<String, dynamic>?),
    geoLabel: j['geo_label'] as String?,
    authorId: j['author_id'] as String?,
  );
}

class SourceRead {
  SourceRead({
    required this.id,
    required this.url,
    required this.domain,
    required this.qualityScore,
    this.title,
    this.publisher,
    this.publishedAt,
    this.kind,
  });

  final String id;
  final String url;
  final String domain;
  final String? title;
  final String? publisher;
  final DateTime? publishedAt;
  final String? kind;
  final int qualityScore;

  factory SourceRead.fromJson(Map<String, dynamic> j) => SourceRead(
    id: j['id'] as String,
    url: j['url'] as String,
    domain: j['domain'] as String,
    title: j['title'] as String?,
    publisher: j['publisher'] as String?,
    publishedAt: j['published_at'] == null
        ? null
        : DateTime.tryParse(j['published_at'] as String),
    kind: j['kind'] as String?,
    qualityScore: j['quality_score'] as int,
  );
}

class EventReference {
  EventReference({
    required this.id,
    required this.label,
    required this.tStart,
    required this.tEnd,
    required this.precision,
    required this.confidence,
    this.detail,
    this.subjectEventId,
    this.geo,
  });

  final String id;
  final String label;
  final double tStart;
  final double tEnd;
  final TimePrecision precision;
  final String? detail;
  final int confidence;
  final String? subjectEventId;
  final GeoPoint? geo;

  factory EventReference.fromJson(Map<String, dynamic> j) => EventReference(
    id: j['id'] as String,
    label: j['label'] as String,
    tStart: _d(j['t_start']),
    tEnd: _d(j['t_end']),
    precision: TimePrecision.parse(j['subject_precision'] as String),
    detail: j['detail'] as String?,
    confidence: j['confidence'] as int,
    subjectEventId: j['subject_event_id'] as String?,
    geo: GeoPoint.fromJson(j['geo'] as Map<String, dynamic>?),
  );
}

class EntityRead {
  EntityRead({
    required this.id,
    required this.kind,
    required this.name,
    this.externalId,
    this.geo,
    this.eventCount,
  });
  final String id;
  final String kind; // place | person | org | topic
  final String name;
  final String? externalId;
  final GeoPoint? geo;
  final int? eventCount; // filled by listing/summary endpoints

  factory EntityRead.fromJson(Map<String, dynamic> j) => EntityRead(
    id: j['id'] as String,
    kind: j['kind'] as String,
    name: j['name'] as String,
    externalId: j['external_id'] as String?,
    geo: GeoPoint.fromJson(j['geo'] as Map<String, dynamic>?),
    eventCount: (j['event_count'] as num?)?.toInt(),
  );
}

class EntityRole {
  EntityRole({required this.entity, required this.role});
  final EntityRead entity;
  final String role; // actor | location | subject | affected

  factory EntityRole.fromJson(Map<String, dynamic> j) => EntityRole(
    entity: EntityRead.fromJson(j['entity'] as Map<String, dynamic>),
    role: j['role'] as String,
  );
}

class MediaRead {
  MediaRead({
    required this.id,
    required this.kind,
    required this.role,
    required this.disposition,
    required this.sensitivity,
    required this.locallyStored,
    required this.status,
    this.embedUrl,
    this.caption,
  });

  final String id;
  final String kind; // image | video | audio | embed
  final String role;
  final String disposition; // pin | archive | link
  final int sensitivity;
  final bool locallyStored;
  final String status;
  final String? embedUrl;
  final String? caption;

  factory MediaRead.fromJson(Map<String, dynamic> j) => MediaRead(
    id: j['id'] as String,
    kind: j['kind'] as String,
    role: j['role'] as String? ?? 'gallery',
    disposition: j['disposition'] as String? ?? 'archive',
    sensitivity: (j['sensitivity'] as num?)?.toInt() ?? 0,
    locallyStored: j['locally_stored'] as bool? ?? false,
    status: j['status'] as String? ?? 'pending',
    embedUrl: j['embed_url'] as String?,
    caption: j['caption'] as String?,
  );
}

class RelatedEvent {
  RelatedEvent({
    required this.event,
    required this.kind,
    required this.weight,
    required this.direction,
    this.origin = 'agent',
    this.addedBy,
    this.heroMediaId,
    this.heroIsClip = false,
  });
  final EventRead event;
  final String kind;
  final double weight;
  final String direction; // back | forward
  final String origin; // user | agent (ADR-0025 §2.4)
  final String? addedBy; // actor id when origin == user

  /// The related event's hero media — so walking left/right to it renders the clip/photo, not a
  /// black card. The API only returns related events that have a displayable hero.
  final String? heroMediaId;
  final bool heroIsClip;

  bool get isUserAdded => origin == 'user';

  factory RelatedEvent.fromJson(Map<String, dynamic> j) => RelatedEvent(
    event: EventRead.fromJson(j['event'] as Map<String, dynamic>),
    kind: j['kind'] as String,
    weight: _d(j['weight']),
    direction: j['direction'] as String,
    origin: j['origin'] as String? ?? 'agent',
    addedBy: j['added_by'] as String?,
    heroMediaId: j['hero_media_id'] as String?,
    heroIsClip: j['hero_is_clip'] as bool? ?? false,
  );
}

class ChainEdge {
  ChainEdge({required this.src, required this.dst, required this.kind, required this.weight});
  final String src;
  final String dst;
  final String kind;
  final double weight;

  factory ChainEdge.fromJson(Map<String, dynamic> j) => ChainEdge(
    src: j['src'] as String,
    dst: j['dst'] as String,
    kind: j['kind'] as String,
    weight: _d(j['weight']),
  );
}

class ChainResponse {
  ChainResponse({required this.root, required this.direction, required this.nodes, required this.edges});
  final String root;
  final String direction;
  final List<EventRead> nodes;
  final List<ChainEdge> edges;

  factory ChainResponse.fromJson(Map<String, dynamic> j) => ChainResponse(
    root: j['root'] as String,
    direction: j['direction'] as String,
    nodes: ((j['nodes'] as List?) ?? [])
        .map((e) => EventRead.fromJson(e as Map<String, dynamic>))
        .toList(),
    edges: ((j['edges'] as List?) ?? [])
        .map((e) => ChainEdge.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class EventDetail extends EventRead {
  EventDetail({
    required super.id,
    required super.title,
    required super.tStart,
    required super.tEnd,
    required super.precision,
    required super.severity,
    required super.confidence,
    required super.sourceCount,
    super.summary,
    super.instant,
    super.category,
    super.geo,
    super.geoLabel,
    super.tags,
    this.body,
    this.sources = const [],
    this.references = const [],
    this.entities = const [],
    this.media = const [],
  });

  final String? body;
  final List<SourceRead> sources;
  final List<EventReference> references;
  final List<EntityRole> entities;
  final List<MediaRead> media;

  factory EventDetail.fromJson(Map<String, dynamic> j) {
    final base = EventRead.fromJson(j);
    return EventDetail(
      id: base.id,
      title: base.title,
      summary: base.summary,
      tStart: base.tStart,
      tEnd: base.tEnd,
      precision: base.precision,
      instant: base.instant,
      category: base.category,
      tags: base.tags,
      severity: base.severity,
      confidence: base.confidence,
      sourceCount: base.sourceCount,
      geo: base.geo,
      geoLabel: base.geoLabel,
      body: j['body'] as String?,
      sources: ((j['sources'] as List?) ?? [])
          .map((e) => SourceRead.fromJson(e as Map<String, dynamic>))
          .toList(),
      references: ((j['references'] as List?) ?? [])
          .map((e) => EventReference.fromJson(e as Map<String, dynamic>))
          .toList(),
      entities: ((j['entities'] as List?) ?? [])
          .map((e) => EntityRole.fromJson(e as Map<String, dynamic>))
          .toList(),
      media: ((j['media'] as List?) ?? [])
          .map((e) => MediaRead.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// Faceted search response (event-presentation.md §5.1, ADR-0022): events plus actor
/// (person/org) and place facets, and whether a live-collection job was enqueued for
/// [subject] (the client then follows /search/stream to refresh as results land).
class SearchResults {
  SearchResults({
    required this.subject,
    this.collecting = false,
    this.events = const [],
    this.actors = const [],
    this.places = const [],
  });

  final String subject;
  final bool collecting;
  final List<EventRead> events;
  final List<EntityRead> actors;
  final List<EntityRead> places;

  bool get isEmpty => events.isEmpty && actors.isEmpty && places.isEmpty;

  factory SearchResults.fromJson(Map<String, dynamic> j) => SearchResults(
    subject: (j['subject'] as String?) ?? '',
    collecting: (j['collecting'] as bool?) ?? false,
    events: ((j['events'] as List?) ?? [])
        .map((e) => EventRead.fromJson(e as Map<String, dynamic>))
        .toList(),
    actors: ((j['actors'] as List?) ?? [])
        .map((e) => EntityRead.fromJson(e as Map<String, dynamic>))
        .toList(),
    places: ((j['places'] as List?) ?? [])
        .map((e) => EntityRead.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class TimelineBucket {
  TimelineBucket({
    required this.tStart,
    required this.tEnd,
    required this.count,
    required this.peakSeverity,
  });

  final double tStart;
  final double tEnd;
  final int count;
  final int peakSeverity;

  factory TimelineBucket.fromJson(Map<String, dynamic> j) => TimelineBucket(
    tStart: _d(j['t_start']),
    tEnd: _d(j['t_end']),
    count: j['count'] as int,
    peakSeverity: j['peak_severity'] as int,
  );
}

/// A place (free-text geo_label) with its event count + a representative point.
/// Drives which countries the silhouette map draws and where to anchor labels.
class SummaryPlace {
  SummaryPlace({required this.label, required this.count, this.lat, this.lon});
  final String label;
  final int count;
  final double? lat;
  final double? lon;

  factory SummaryPlace.fromJson(Map<String, dynamic> j) => SummaryPlace(
    label: j['label'] as String,
    count: j['count'] as int,
    lat: (j['lat'] as num?)?.toDouble(),
    lon: (j['lon'] as num?)?.toDouble(),
  );
}

/// A lightweight representative event for a timeframe montage (no body/sources/media list).
class SummaryRep {
  SummaryRep({
    required this.id,
    required this.title,
    required this.tStart,
    required this.precision,
    required this.severity,
    this.geo,
    this.geoLabel,
    this.heroMediaId,
  });
  final String id;
  final String title;
  final double tStart;
  final TimePrecision precision;
  final int severity;
  final GeoPoint? geo;
  final String? geoLabel;
  final String? heroMediaId;

  factory SummaryRep.fromJson(Map<String, dynamic> j) => SummaryRep(
    id: j['id'] as String,
    title: j['title'] as String,
    tStart: _d(j['t_start']),
    precision: TimePrecision.parse(j['time_precision'] as String),
    severity: j['severity'] as int,
    geo: GeoPoint.fromJson(j['geo'] as Map<String, dynamic>?),
    geoLabel: j['geo_label'] as String?,
    heroMediaId: j['hero_media_id'] as String?,
  );
}

/// Bandwidth-safe distillation of a whole timeframe (many events → one view).
class TimelineSummary {
  TimelineSummary({
    required this.t0,
    required this.t1,
    required this.total,
    this.bucketYears,
    this.buckets = const [],
    this.topEntities = const [],
    this.topPlaces = const [],
    this.representatives = const [],
  });

  final double t0;
  final double t1;
  final int total;
  final double? bucketYears;
  final List<TimelineBucket> buckets;
  final List<EntityRead> topEntities;
  final List<SummaryPlace> topPlaces;
  final List<SummaryRep> representatives;

  factory TimelineSummary.fromJson(Map<String, dynamic> j) => TimelineSummary(
    t0: _d(j['t0']),
    t1: _d(j['t1']),
    total: j['total'] as int,
    bucketYears: j['bucket_years'] == null ? null : _d(j['bucket_years']),
    buckets: ((j['buckets'] as List?) ?? [])
        .map((e) => TimelineBucket.fromJson(e as Map<String, dynamic>))
        .toList(),
    topEntities: ((j['top_entities'] as List?) ?? [])
        .map((e) => EntityRead.fromJson(e as Map<String, dynamic>))
        .toList(),
    topPlaces: ((j['top_places'] as List?) ?? [])
        .map((e) => SummaryPlace.fromJson(e as Map<String, dynamic>))
        .toList(),
    representatives: ((j['representatives'] as List?) ?? [])
        .map((e) => SummaryRep.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

/// One threaded comment on an event (data-model.md §3.5 / ADR-0025). Replies point at a
/// parent via [parentId]; a null parent is a top-level comment. The article builds the
/// tree client-side from the flat, oldest-first list the API returns. Soft-removed
/// comments come back with status `removed` (kept so reply threads don't collapse).
/// Aggregate engagement counts for an event (`GET /events/{id}/stats`) — the numbers shown
/// on each feed action button.
class EventStats {
  EventStats({
    required this.eventId,
    this.reactions = 0,
    this.comments = 0,
    this.promoteScore = 0,
    this.promotesUp = 0,
    this.promotesDown = 0,
    this.followers = 0,
    this.bookmarks = 0,
    Map<String, int>? reactionCounts,
  }) : reactionCounts = reactionCounts ?? const {};

  final String eventId;
  final int reactions;
  final int comments;
  final int promoteScore;
  final int promotesUp;
  final int promotesDown;
  final int followers;
  final int bookmarks;
  final Map<String, int> reactionCounts;

  factory EventStats.fromJson(Map<String, dynamic> j) => EventStats(
    eventId: j['event_id'] as String,
    reactions: (j['reactions'] as num?)?.toInt() ?? 0,
    comments: (j['comments'] as num?)?.toInt() ?? 0,
    promoteScore: (j['promote_score'] as num?)?.toInt() ?? 0,
    promotesUp: (j['promotes_up'] as num?)?.toInt() ?? 0,
    promotesDown: (j['promotes_down'] as num?)?.toInt() ?? 0,
    followers: (j['followers'] as num?)?.toInt() ?? 0,
    bookmarks: (j['bookmarks'] as num?)?.toInt() ?? 0,
    reactionCounts: (j['reaction_counts'] as Map?)?.map(
          (k, v) => MapEntry(k as String, (v as num).toInt()),
        ) ??
        const {},
  );
}

/// The public identity of a comment's author (avatar + profile link).
class CommentAuthor {
  CommentAuthor({required this.id, required this.handle, this.displayName, this.avatarUrl});
  final String id;
  final String handle;
  final String? displayName;
  final String? avatarUrl;

  String get label => displayName ?? handle;

  factory CommentAuthor.fromJson(Map<String, dynamic> j) => CommentAuthor(
    id: j['id'] as String,
    handle: j['handle'] as String? ?? '',
    displayName: j['display_name'] as String?,
    avatarUrl: j['avatar_url'] as String?,
  );
}

class CommentRead {
  CommentRead({
    required this.id,
    required this.eventId,
    required this.userId,
    required this.body,
    required this.score,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.parentId,
    this.author,
    Map<String, int>? reactions,
    List<String>? myReactions,
  })  : reactions = reactions ?? const {},
        myReactions = myReactions ?? const [];

  final String id;
  final String eventId;
  final String userId;
  final String? parentId;
  final String body;
  final int score;
  final String status; // visible | removed | hidden
  final DateTime createdAt;
  final DateTime updatedAt;
  final CommentAuthor? author;

  /// Aggregate reaction counts per kind on this comment, + the caller's own kinds.
  final Map<String, int> reactions;
  final List<String> myReactions;

  bool get isRemoved => status == 'removed';

  static DateTime _dt(Object? v) =>
      DateTime.tryParse(v as String? ?? '') ?? DateTime.fromMillisecondsSinceEpoch(0);

  factory CommentRead.fromJson(Map<String, dynamic> j) => CommentRead(
    id: j['id'] as String,
    eventId: j['event_id'] as String,
    userId: j['user_id'] as String,
    parentId: j['parent_id'] as String?,
    body: j['body'] as String? ?? '',
    score: (j['score'] as num?)?.toInt() ?? 0,
    status: j['status'] as String? ?? 'visible',
    createdAt: _dt(j['created_at']),
    updatedAt: _dt(j['updated_at']),
    author: j['author'] is Map<String, dynamic>
        ? CommentAuthor.fromJson(j['author'] as Map<String, dynamic>)
        : null,
    reactions: (j['reactions'] as Map?)?.map(
          (k, v) => MapEntry(k as String, (v as num).toInt()),
        ) ??
        const {},
    myReactions:
        (j['my_reactions'] as List?)?.map((e) => e as String).toList() ?? const [],
  );
}

/// A public user profile (`GET /users/{id}`): identity, reputation, follow counts + relation.
class UserProfile {
  UserProfile({
    required this.id,
    required this.handle,
    this.displayName,
    this.avatarUrl,
    this.reputation = 0,
    this.followers = 0,
    this.following = 0,
    this.isFollowing = false,
    this.isSelf = false,
  });

  final String id;
  final String handle;
  final String? displayName;
  final String? avatarUrl;
  final int reputation;
  final int followers;
  final int following;
  final bool isFollowing;
  final bool isSelf;

  String get label => displayName ?? handle;

  factory UserProfile.fromJson(Map<String, dynamic> j) => UserProfile(
    id: j['id'] as String,
    handle: j['handle'] as String? ?? '',
    displayName: j['display_name'] as String?,
    avatarUrl: j['avatar_url'] as String?,
    reputation: (j['reputation'] as num?)?.toInt() ?? 0,
    followers: (j['followers'] as num?)?.toInt() ?? 0,
    following: (j['following'] as num?)?.toInt() ?? 0,
    isFollowing: j['is_following'] as bool? ?? false,
    isSelf: j['is_self'] as bool? ?? false,
  );
}

/// A user in a follower/following list (identity + whether the caller follows them).
class UserSummary {
  UserSummary({
    required this.id,
    required this.handle,
    this.displayName,
    this.avatarUrl,
    this.following = false,
  });

  final String id;
  final String handle;
  final String? displayName;
  final String? avatarUrl;
  final bool following;

  String get label => displayName ?? handle;

  factory UserSummary.fromJson(Map<String, dynamic> j) => UserSummary(
    id: j['id'] as String,
    handle: j['handle'] as String? ?? '',
    displayName: j['display_name'] as String?,
    avatarUrl: j['avatar_url'] as String?,
    following: j['following'] as bool? ?? false,
  );
}

/// Aggregate reactions for an event (ADR-0025 §2.2): per-kind counts plus the kinds the
/// calling actor has set (`mine`). The POST toggle returns the same aggregate so the UI
/// reconciles to the server truth after its optimistic update.
class ReactionSummary {
  ReactionSummary({
    required this.eventId,
    required this.counts,
    required this.mine,
  });

  final String eventId;
  final Map<String, int> counts; // kind -> count
  final Set<String> mine; // kinds the actor has set

  static const List<String> kinds = ['like', 'dislike', 'important', 'doubt'];

  int countOf(String kind) => counts[kind] ?? 0;
  bool isMine(String kind) => mine.contains(kind);

  static Map<String, int> _counts(Object? v) {
    final m = (v as Map?) ?? const {};
    return m.map((k, val) => MapEntry(k as String, (val as num).toInt()));
  }

  factory ReactionSummary.fromJson(Map<String, dynamic> j) => ReactionSummary(
    eventId: j['event_id'] as String? ?? '',
    counts: _counts(j['counts']),
    mine: ((j['mine'] as List?) ?? const []).map((e) => e as String).toSet(),
  );

  /// The POST toggle response carries `{kind, active, counts, mine}` — same aggregate.
  factory ReactionSummary.fromToggle(Map<String, dynamic> j) =>
      ReactionSummary.fromJson(j);
}

/// Credibility votes for an event's sources (ADR-0025 §2.3). [tallies] maps each source
/// id to its per-verdict counts; [mine] maps each source id to the verdict the actor cast
/// (absent → not yet voted).
class SourceVotes {
  SourceVotes({required this.eventId, required this.tallies, required this.mine});

  final String eventId;
  final Map<String, Map<String, int>> tallies; // source_id -> verdict -> count
  final Map<String, String> mine; // source_id -> verdict

  static const List<String> verdicts = ['corroborate', 'dispute', 'irrelevant'];

  Map<String, int> talliesFor(String sourceId) => tallies[sourceId] ?? const {};
  String? mineFor(String sourceId) => mine[sourceId];

  static Map<String, Map<String, int>> _tallies(Object? v) {
    final m = (v as Map?) ?? const {};
    return m.map((sid, verdicts) {
      final vm = (verdicts as Map?) ?? const {};
      return MapEntry(
        sid as String,
        vm.map((k, c) => MapEntry(k as String, (c as num).toInt())),
      );
    });
  }

  static Map<String, String> _mine(Object? v) {
    final m = (v as Map?) ?? const {};
    return m.map((sid, verdict) => MapEntry(sid as String, verdict as String));
  }

  factory SourceVotes.fromJson(Map<String, dynamic> j) => SourceVotes(
    eventId: j['event_id'] as String? ?? '',
    tallies: _tallies(j['tallies']),
    mine: _mine(j['mine']),
  );
}

// ── Social graph + promotion + feed (social-and-feed §2/§4, ADR-0028). ──

/// Follower/following counts for a follow target (`GET /follow/counts`).
class FollowCounts {
  FollowCounts({required this.followers, required this.following});
  final int followers;
  final int following;

  factory FollowCounts.fromJson(Map<String, dynamic> j) => FollowCounts(
    followers: (j['followers'] as num?)?.toInt() ?? 0,
    following: (j['following'] as num?)?.toInt() ?? 0,
  );
}

/// The tally returned by `POST /promote`: the caller's own vote ([mine] ∈ -1|0|1), the net
/// [score], and the raw [up]/[down] counts. Drives the up/down affordances' selected state.
class PromoteResult {
  PromoteResult({
    required this.mine,
    required this.score,
    required this.up,
    required this.down,
  });
  final int mine;
  final int score;
  final int up;
  final int down;

  factory PromoteResult.fromJson(Map<String, dynamic> j) => PromoteResult(
    mine: (j['mine'] as num?)?.toInt() ?? 0,
    score: (j['score'] as num?)?.toInt() ?? 0,
    up: (j['up'] as num?)?.toInt() ?? 0,
    down: (j['down'] as num?)?.toInt() ?? 0,
  );
}

/// One weighted interest the recommender learned (`GET /me/interests`): a label + its decayed
/// weight, grouped by [kind] (entity | category | place | author).
class InterestItem {
  InterestItem({
    required this.kind,
    required this.label,
    required this.weight,
    this.id,
  });
  final String kind;
  final String label;
  final double weight;
  final String? id;

  factory InterestItem.fromJson(Map<String, dynamic> j) => InterestItem(
    kind: (j['kind'] ?? j['type'] ?? 'topic') as String,
    label: (j['label'] ?? j['name'] ?? '') as String,
    weight: (j['weight'] as num?)?.toDouble() ?? 0,
    id: j['id'] as String?,
  );
}

/// The user's activity-driven interest profile (`GET /me/interests`, ADR-0028).
class InterestProfile {
  InterestProfile({this.items = const [], this.sampleSize = 0});
  final List<InterestItem> items;

  /// The number of activity rows the profile was computed from (`sample_size`); 0 means the
  /// recommender has nothing to learn from yet (drives the empty-state copy).
  final int sampleSize;

  bool get isEmpty => items.isEmpty;

  factory InterestProfile.fromJson(Map<String, dynamic> j) {
    final sample = (j['sample_size'] as num?)?.toInt() ?? 0;
    // Tolerate either a flat `interests`/`items` list or per-kind buckets.
    final flat = (j['interests'] ?? j['items']) as List?;
    if (flat != null) {
      return InterestProfile(
        items: flat
            .map((e) => InterestItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        sampleSize: sample,
      );
    }
    // The live `/me/interests` shape (chronos_core.schemas.social.InterestProfile): per-kind
    // `{id-or-name: weight}` maps. `categories` keys are display names; `entities`/`places`/
    // `sources` key by uuid (no name on the wire), so the id doubles as the label for now.
    final out = <InterestItem>[];
    for (final kind in const ['entities', 'categories', 'places', 'sources']) {
      final bucket = j[kind];
      if (bucket is Map) {
        bucket.forEach((key, weight) {
          out.add(InterestItem(
            kind: kind,
            label: key.toString(),
            weight: (weight as num?)?.toDouble() ?? 0,
            id: kind == 'categories' ? null : key.toString(),
          ));
        });
      } else if (bucket is List) {
        for (final e in bucket) {
          final m = Map<String, dynamic>.from(e as Map);
          m['kind'] ??= kind;
          out.add(InterestItem.fromJson(m));
        }
      }
    }
    out.sort((a, b) => b.weight.compareTo(a.weight));
    return InterestProfile(items: out, sampleSize: sample);
  }
}

/// The result of `POST /upload` (ADR-0029): the created event + hero media id and the
/// moderation [status] (`pending` until the queue clears, then `visible`).
class UploadResult {
  UploadResult({this.eventId, this.mediaId, this.status = 'pending', this.event});
  final String? eventId;
  final String? mediaId;
  final String status;
  final EventRead? event;

  bool get isPending => status == 'pending';

  factory UploadResult.fromJson(Map<String, dynamic> j) {
    final ev = j['event'] is Map<String, dynamic>
        ? EventRead.fromJson(j['event'] as Map<String, dynamic>)
        : null;
    return UploadResult(
      eventId: (j['event_id'] ?? ev?.id) as String?,
      mediaId: (j['media_id'] ?? j['hero_media_id']) as String?,
      status: (j['status'] as String?) ?? 'pending',
      event: ev,
    );
  }
}

// ── Auth & account (Phase 4-G, ADR-0026). Mirror the live /auth + /account DTOs. ──

/// A sign-in provider offered by the backend (`GET /auth/providers`). The set is
/// config-driven and **may be empty** until credentials are configured — the login UI
/// renders that case as "no providers configured".
class AuthProvider {
  AuthProvider({required this.name, this.displayName});

  /// The slug used in `/auth/{name}/login` (e.g. `google`, `apple`).
  final String name;

  /// Human label; falls back to a title-cased [name] when the server omits it.
  final String? displayName;

  String get label =>
      displayName ?? (name.isEmpty ? name : name[0].toUpperCase() + name.substring(1));

  factory AuthProvider.fromJson(Map<String, dynamic> j) => AuthProvider(
    // The backend's ProviderInfo carries `id`; tolerate `name` for older shapes.
    name: (j['id'] ?? j['name']) as String,
    displayName: j['display_name'] as String?,
  );
}

/// The sign-in options the backend offers (`GET /auth/providers`): the OAuth [providers]
/// (may be empty) plus whether the self-contained [devLogin] (email-code) path is available.
class AuthOptions {
  AuthOptions({required this.providers, this.devLogin = false});
  final List<AuthProvider> providers;
  final bool devLogin;

  factory AuthOptions.fromJson(Map<String, dynamic> j) => AuthOptions(
    providers: ((j['providers'] as List?) ?? const [])
        .map((e) => AuthProvider.fromJson(e as Map<String, dynamic>))
        .toList(),
    devLogin: (j['dev_login'] as bool?) ?? false,
  );
}

/// The authorize URL + PKCE round-trip material from `GET /auth/{provider}/login`. The
/// client opens [authorizeUrl] in a browser and echoes [state] (+ [codeVerifier]) back on
/// the callback so the backend can finish the exchange.
class LoginChallenge {
  LoginChallenge({required this.authorizeUrl, this.state, this.codeVerifier});
  final String authorizeUrl;
  final String? state;
  final String? codeVerifier;

  factory LoginChallenge.fromJson(Map<String, dynamic> j) => LoginChallenge(
    authorizeUrl: (j['authorize_url'] ?? j['url'] ?? j['authorizeUrl']) as String,
    state: j['state'] as String?,
    codeVerifier: (j['code_verifier'] ?? j['verifier'] ?? j['pkce_verifier']) as String?,
  );
}

/// The signed-in user (`GET /account/me`, also returned by the callback). Reads stay open
/// for anonymous; this is present only once a session exists.
class SessionUser {
  SessionUser({
    required this.id,
    this.email,
    this.displayName,
    this.avatarUrl,
    this.bio,
    this.emailVerified = false,
    PrivacySettings? privacy,
  }) : privacy = privacy ?? PrivacySettings();

  final String id;
  final String? email;
  final String? displayName;
  final String? avatarUrl;
  final String? bio;
  final bool emailVerified;
  final PrivacySettings privacy;

  String get label => displayName ?? email ?? id;

  factory SessionUser.fromJson(Map<String, dynamic> j) => SessionUser(
    id: (j['id'] ?? j['user_id'] ?? '') as String,
    email: j['email'] as String?,
    displayName: (j['display_name'] ?? j['name']) as String?,
    avatarUrl: (j['avatar_url'] ?? j['picture']) as String?,
    bio: j['bio'] as String?,
    emailVerified: (j['email_verified'] as bool?) ??
        (j['verified'] as bool?) ??
        false,
    privacy: j['privacy'] is Map<String, dynamic>
        ? PrivacySettings.fromJson(j['privacy'] as Map<String, dynamic>)
        : null,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'email': ?email,
    'display_name': ?displayName,
    'avatar_url': ?avatarUrl,
    'bio': ?bio,
    'email_verified': emailVerified,
    'privacy': privacy.toJson(),
  };
}

/// Per-profile privacy settings (each facet's minimum viewable audience + default post
/// audience). Mirrors the backend ``PrivacySettings``; absent ⇒ all-public.
class PrivacySettings {
  PrivacySettings({
    this.bio = 'public',
    this.posts = 'public',
    this.followers = 'public',
    this.following = 'public',
    this.interactions = 'public',
    this.defaultPostAudience = 'public',
  });

  final String bio;
  final String posts;
  final String followers;
  final String following;
  final String interactions;
  final String defaultPostAudience; // public|followers|friends

  factory PrivacySettings.fromJson(Map<String, dynamic> j) => PrivacySettings(
    bio: j['bio'] as String? ?? 'public',
    posts: j['posts'] as String? ?? 'public',
    followers: j['followers'] as String? ?? 'public',
    following: j['following'] as String? ?? 'public',
    interactions: j['interactions'] as String? ?? 'public',
    defaultPostAudience: j['default_post_audience'] as String? ?? 'public',
  );

  Map<String, dynamic> toJson() => {
    'bio': bio,
    'posts': posts,
    'followers': followers,
    'following': following,
    'interactions': interactions,
    'default_post_audience': defaultPostAudience,
  };

  PrivacySettings copyWith({
    String? bio,
    String? posts,
    String? followers,
    String? following,
    String? interactions,
    String? defaultPostAudience,
  }) =>
      PrivacySettings(
        bio: bio ?? this.bio,
        posts: posts ?? this.posts,
        followers: followers ?? this.followers,
        following: following ?? this.following,
        interactions: interactions ?? this.interactions,
        defaultPostAudience: defaultPostAudience ?? this.defaultPostAudience,
      );
}

/// The result of a completed OAuth callback (`/auth/{provider}/callback`): the session JWT
/// the client stores + attaches as a Bearer, plus the resolved [user].
class AuthSession {
  AuthSession({required this.token, this.user});
  final String token;
  final SessionUser? user;

  factory AuthSession.fromJson(Map<String, dynamic> j) => AuthSession(
    token: (j['token'] ?? j['session_token'] ?? j['access_token'] ?? j['jwt']) as String,
    user: j['user'] is Map<String, dynamic>
        ? SessionUser.fromJson(j['user'] as Map<String, dynamic>)
        : null,
  );
}

/// The current versioned agreement (`GET /auth/agreement`): the version the user must
/// accept and a URL to the full Terms/privacy document.
class Agreement {
  Agreement({required this.version, this.url, this.summary});
  final String version;
  final String? url;
  final String? summary;

  factory Agreement.fromJson(Map<String, dynamic> j) => Agreement(
    version: (j['version'] ?? '') as String,
    url: j['url'] as String?,
    summary: j['summary'] as String?,
  );
}

/// Whether the signed-in user has accepted the current agreement version
/// (`GET /auth/agreement/status`). [accepted] gates interaction (re-prompt on version change).
class AgreementStatus {
  AgreementStatus({required this.accepted, this.acceptedVersion, this.currentVersion});
  final bool accepted;
  final String? acceptedVersion;
  final String? currentVersion;

  factory AgreementStatus.fromJson(Map<String, dynamic> j) => AgreementStatus(
    accepted: (j['accepted'] as bool?) ?? false,
    acceptedVersion: j['accepted_version'] as String?,
    currentVersion: j['current_version'] as String?,
  );
}

class TimelineResponse {
  TimelineResponse({
    required this.mode,
    required this.t0,
    required this.t1,
    this.bucketYears,
    this.events = const [],
    this.buckets = const [],
  });

  final String mode; // "events" | "buckets"
  final double t0;
  final double t1;
  final double? bucketYears;
  final List<EventRead> events;
  final List<TimelineBucket> buckets;

  bool get isBuckets => mode == 'buckets';

  factory TimelineResponse.fromJson(Map<String, dynamic> j) => TimelineResponse(
    mode: j['mode'] as String,
    t0: _d(j['t0']),
    t1: _d(j['t1']),
    bucketYears: j['bucket_years'] == null ? null : _d(j['bucket_years']),
    events: ((j['events'] as List?) ?? [])
        .map((e) => EventRead.fromJson(e as Map<String, dynamic>))
        .toList(),
    buckets: ((j['buckets'] as List?) ?? [])
        .map((e) => TimelineBucket.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}
