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
  });
  final EventRead event;
  final String kind;
  final double weight;
  final String direction; // back | forward
  final String origin; // user | agent (ADR-0025 §2.4)
  final String? addedBy; // actor id when origin == user

  bool get isUserAdded => origin == 'user';

  factory RelatedEvent.fromJson(Map<String, dynamic> j) => RelatedEvent(
    event: EventRead.fromJson(j['event'] as Map<String, dynamic>),
    kind: j['kind'] as String,
    weight: _d(j['weight']),
    direction: j['direction'] as String,
    origin: j['origin'] as String? ?? 'agent',
    addedBy: j['added_by'] as String?,
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
  });

  final String id;
  final String eventId;
  final String userId;
  final String? parentId;
  final String body;
  final int score;
  final String status; // visible | removed | hidden
  final DateTime createdAt;
  final DateTime updatedAt;

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
