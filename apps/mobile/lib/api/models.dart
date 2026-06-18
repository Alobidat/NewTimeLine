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
  });

  final String? body;
  final List<SourceRead> sources;
  final List<EventReference> references;

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
    );
  }
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
