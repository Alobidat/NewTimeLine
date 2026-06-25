/// DTOs mirroring chronos_core.schemas.admin (the Admin API responses).
library;

class HealthView {
  HealthView({
    required this.status,
    this.level = 'ok',
    this.message,
    this.lastRunAt,
    this.lastStatus,
    this.runs = 0,
    this.successRate,
  });

  final String status; // never|running|ok|stale|error OR ok|down|degraded|unknown
  final String level; // ok | warning | degraded | critical
  final String? message;
  final DateTime? lastRunAt;
  final String? lastStatus;
  final int runs;
  final double? successRate;

  factory HealthView.fromJson(Map<String, dynamic> j) => HealthView(
    status: j['status'] as String? ?? 'never',
    level: j['level'] as String? ?? 'ok',
    message: j['message'] as String?,
    lastRunAt: _dt(j['last_run_at']),
    lastStatus: j['last_status'] as String?,
    runs: (j['runs'] as num?)?.toInt() ?? 0,
    successRate: (j['success_rate'] as num?)?.toDouble(),
  );
}

class ComponentView {
  ComponentView({
    required this.id,
    required this.kind,
    required this.title,
    required this.description,
    required this.capabilities,
    required this.actions,
    required this.health,
    this.configPrefix,
    this.enabled,
    this.plane,
    this.latestMetrics,
    this.doc,
  });

  final String id;
  final String kind;
  final String title;
  final String description;
  final List<String> capabilities;
  final List<String> actions;
  final HealthView health;
  final String? configPrefix;
  final bool? enabled;
  final String? plane;
  final Map<String, dynamic>? latestMetrics;
  final String? doc;

  factory ComponentView.fromJson(Map<String, dynamic> j) => ComponentView(
    id: j['id'] as String,
    kind: j['kind'] as String,
    title: j['title'] as String,
    description: j['description'] as String? ?? '',
    capabilities: _strList(j['capabilities']),
    actions: _strList(j['actions']),
    health: HealthView.fromJson(j['health'] as Map<String, dynamic>),
    configPrefix: j['config_prefix'] as String?,
    enabled: j['enabled'] as bool?,
    plane: j['plane'] as String?,
    latestMetrics: (j['latest_metrics'] as Map?)?.cast<String, dynamic>(),
    doc: j['doc'] as String?,
  );
}

class ComponentDetail extends ComponentView {
  ComponentDetail({
    required super.id,
    required super.kind,
    required super.title,
    required super.description,
    required super.capabilities,
    required super.actions,
    required super.health,
    super.configPrefix,
    super.enabled,
    super.plane,
    super.latestMetrics,
    super.doc,
    required this.config,
    required this.recentRuns,
  });

  final List<ConfigEntry> config;
  final List<RunView> recentRuns;

  factory ComponentDetail.fromJson(Map<String, dynamic> j) {
    final base = ComponentView.fromJson(j);
    return ComponentDetail(
      id: base.id, kind: base.kind, title: base.title, description: base.description,
      capabilities: base.capabilities, actions: base.actions, health: base.health,
      configPrefix: base.configPrefix, enabled: base.enabled, doc: base.doc,
      plane: base.plane, latestMetrics: base.latestMetrics,
      config: (j['config'] as List? ?? [])
          .map((e) => ConfigEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
      recentRuns: (j['recent_runs'] as List? ?? [])
          .map((e) => RunView.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class RunView {
  RunView({
    required this.id,
    required this.componentId,
    required this.command,
    required this.status,
    required this.startedAt,
    this.finishedAt,
    this.stats,
    this.error,
  });

  final String id;
  final String componentId;
  final String command;
  final String status;
  final DateTime startedAt;
  final DateTime? finishedAt;
  final Map<String, dynamic>? stats;
  final String? error;

  factory RunView.fromJson(Map<String, dynamic> j) => RunView(
    id: j['id'] as String,
    componentId: j['component_id'] as String,
    command: j['command'] as String,
    status: j['status'] as String,
    startedAt: _dt(j['started_at'])!,
    finishedAt: _dt(j['finished_at']),
    stats: (j['stats'] as Map?)?.cast<String, dynamic>(),
    error: j['error'] as String?,
  );
}

class ConfigEntry {
  ConfigEntry({
    required this.key,
    required this.type,
    required this.scope,
    required this.label,
    required this.help,
    required this.value,
    this.componentId,
    this.defaultValue,
    this.minimum,
    this.maximum,
    this.choices,
    this.secret = false,
  });

  final String key;
  final String type; // bool | int | float | string | enum | list | json
  final String scope;
  final String label;
  final String help;
  final dynamic value;
  final String? componentId;
  final dynamic defaultValue;
  final double? minimum;
  final double? maximum;
  final List<String>? choices;
  final bool secret;

  factory ConfigEntry.fromJson(Map<String, dynamic> j) => ConfigEntry(
    key: j['key'] as String,
    type: j['type'] as String,
    scope: j['scope'] as String,
    label: j['label'] as String? ?? j['key'] as String,
    help: j['help'] as String? ?? '',
    value: j['value'],
    componentId: j['component_id'] as String?,
    defaultValue: j['default'],
    minimum: (j['minimum'] as num?)?.toDouble(),
    maximum: (j['maximum'] as num?)?.toDouble(),
    choices: j['choices'] == null ? null : _strList(j['choices']),
    secret: j['secret'] as bool? ?? false,
  );
}

class OverviewView {
  OverviewView({required this.components, required this.counts, required this.recentRuns});

  final List<ComponentView> components;
  final Map<String, int> counts;
  final List<RunView> recentRuns;

  factory OverviewView.fromJson(Map<String, dynamic> j) => OverviewView(
    components: (j['components'] as List? ?? [])
        .map((e) => ComponentView.fromJson(e as Map<String, dynamic>))
        .toList(),
    counts: (j['counts'] as Map? ?? {}).map((k, v) => MapEntry(k as String, (v as num).toInt())),
    recentRuns: (j['recent_runs'] as List? ?? [])
        .map((e) => RunView.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class StorageView {
  StorageView({
    required this.mediaByStatus,
    required this.mediaByDisposition,
    required this.mediaStoredBytes,
    required this.totals,
  });

  final Map<String, int> mediaByStatus;
  final Map<String, int> mediaByDisposition;
  final int mediaStoredBytes;
  final Map<String, int> totals;

  factory StorageView.fromJson(Map<String, dynamic> j) => StorageView(
    mediaByStatus: _intMap(j['media_by_status']),
    mediaByDisposition: _intMap(j['media_by_disposition']),
    mediaStoredBytes: (j['media_stored_bytes'] as num?)?.toInt() ?? 0,
    totals: _intMap(j['totals']),
  );
}

class SystemView {
  SystemView({
    required this.environment,
    required this.database,
    required this.configKeys,
    required this.components,
    required this.runningAgents,
  });

  final String environment;
  final String database;
  final int configKeys;
  final int components;
  final int runningAgents;

  factory SystemView.fromJson(Map<String, dynamic> j) => SystemView(
    environment: j['environment'] as String? ?? '?',
    database: j['database'] as String? ?? '?',
    configKeys: (j['config_keys'] as num?)?.toInt() ?? 0,
    components: (j['components'] as num?)?.toInt() ?? 0,
    runningAgents: (j['running_agents'] as num?)?.toInt() ?? 0,
  );
}

/// Latest host resource snapshot (the gauges atop the System Health dashboard).
class HostMetricsView {
  HostMetricsView({required this.metrics, this.updatedAt});

  final Map<String, double> metrics; // disk/mem/cpu/load latest values
  final DateTime? updatedAt;

  double? operator [](String k) => metrics[k];

  factory HostMetricsView.fromJson(Map<String, dynamic> j) => HostMetricsView(
    metrics: (j['metrics'] as Map? ?? const {})
        .map((k, v) => MapEntry(k as String, (v as num).toDouble())),
    updatedAt: _dt(j['updated_at']),
  );
}

/// Components sharing a plane (a dashboard section) + the plane's worst-case level.
class PlaneGroup {
  PlaneGroup({required this.plane, required this.level, required this.components});

  final String plane; // edge | api | processing | store | client
  final String level; // ok | warning | degraded | critical
  final List<ComponentView> components;

  factory PlaneGroup.fromJson(Map<String, dynamic> j) => PlaneGroup(
    plane: j['plane'] as String? ?? 'other',
    level: j['level'] as String? ?? 'ok',
    components: (j['components'] as List? ?? const [])
        .map((e) => ComponentView.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

/// The System Health dashboard payload: components grouped by plane + host gauges.
class HealthTreeView {
  HealthTreeView({
    required this.planes,
    required this.host,
    required this.level,
    this.generatedAt,
  });

  final List<PlaneGroup> planes;
  final HostMetricsView host;
  final String level; // worst level across the whole system
  final DateTime? generatedAt;

  factory HealthTreeView.fromJson(Map<String, dynamic> j) => HealthTreeView(
    planes: (j['planes'] as List? ?? const [])
        .map((e) => PlaneGroup.fromJson(e as Map<String, dynamic>))
        .toList(),
    host: HostMetricsView.fromJson((j['host'] as Map?)?.cast<String, dynamic>() ?? const {}),
    level: j['level'] as String? ?? 'ok',
    generatedAt: _dt(j['generated_at']),
  );
}

/// One time-series sample.
class MetricPoint {
  MetricPoint({required this.ts, required this.value});
  final DateTime ts;
  final double value;

  factory MetricPoint.fromJson(Map<String, dynamic> j) =>
      MetricPoint(ts: _dt(j['ts'])!, value: (j['value'] as num).toDouble());
}

/// A component's readings for one metric over a window (chart/sparkline source).
class MetricSeries {
  MetricSeries({required this.componentId, required this.metric, this.unit, required this.points});
  final String componentId;
  final String metric;
  final String? unit;
  final List<MetricPoint> points;

  factory MetricSeries.fromJson(Map<String, dynamic> j) => MetricSeries(
    componentId: j['component_id'] as String,
    metric: j['metric'] as String,
    unit: j['unit'] as String?,
    points: (j['points'] as List? ?? const [])
        .map((e) => MetricPoint.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

/// AI-user (bot) roster row — mirrors chronos_core.schemas.admin_bots.BotView.
class BotView {
  BotView({
    required this.id,
    required this.handle,
    required this.interests,
    required this.enabled,
    required this.postsEnabled,
    required this.interactsEnabled,
    required this.postsCount,
    required this.interactionsCount,
    this.displayName,
    this.avatarUrl,
    this.tone,
    this.lastPostAt,
    this.lastInteractAt,
  });

  final String id;
  final String handle;
  final String? displayName;
  final String? avatarUrl;
  final List<String> interests;
  final String? tone;
  final bool enabled;
  final bool postsEnabled;
  final bool interactsEnabled;
  final int postsCount;
  final int interactionsCount;
  final DateTime? lastPostAt;
  final DateTime? lastInteractAt;

  String get label => (displayName ?? handle);

  factory BotView.fromJson(Map<String, dynamic> j) => BotView(
    id: j['id'] as String,
    handle: j['handle'] as String,
    displayName: j['display_name'] as String?,
    avatarUrl: j['avatar_url'] as String?,
    interests: _strList(j['interests']),
    tone: j['tone'] as String?,
    enabled: j['enabled'] as bool? ?? true,
    postsEnabled: j['posts_enabled'] as bool? ?? true,
    interactsEnabled: j['interacts_enabled'] as bool? ?? true,
    postsCount: (j['posts_count'] as num?)?.toInt() ?? 0,
    interactionsCount: (j['interactions_count'] as num?)?.toInt() ?? 0,
    lastPostAt: _dt(j['last_post_at']),
    lastInteractAt: _dt(j['last_interact_at']),
  );
}

class BotRoster {
  BotRoster({required this.total, required this.enabled, required this.bots});
  final int total;
  final int enabled;
  final List<BotView> bots;

  factory BotRoster.fromJson(Map<String, dynamic> j) => BotRoster(
    total: (j['total'] as num?)?.toInt() ?? 0,
    enabled: (j['enabled'] as num?)?.toInt() ?? 0,
    bots: (j['bots'] as List? ?? const [])
        .map((e) => BotView.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class BotPostView {
  BotPostView({required this.eventId, required this.title, required this.status, this.category});
  final String eventId;
  final String title;
  final String status;
  final String? category;

  factory BotPostView.fromJson(Map<String, dynamic> j) => BotPostView(
    eventId: j['event_id'] as String,
    title: j['title'] as String? ?? '',
    status: j['status'] as String? ?? '',
    category: j['category'] as String?,
  );
}

class BotCommentView {
  BotCommentView({required this.eventId, required this.body});
  final String eventId;
  final String body;

  factory BotCommentView.fromJson(Map<String, dynamic> j) =>
      BotCommentView(eventId: j['event_id'] as String, body: j['body'] as String? ?? '');
}

class BotDetail extends BotView {
  BotDetail({
    required super.id,
    required super.handle,
    required super.interests,
    required super.enabled,
    required super.postsEnabled,
    required super.interactsEnabled,
    required super.postsCount,
    required super.interactionsCount,
    super.displayName,
    super.avatarUrl,
    super.tone,
    super.lastPostAt,
    super.lastInteractAt,
    this.persona,
    required this.postCadenceMin,
    required this.interactCadenceMin,
    required this.qualityThreshold,
    required this.dailyPostCap,
    required this.dailyInteractCap,
    required this.followers,
    required this.following,
    required this.recentPosts,
    required this.recentComments,
  });

  final String? persona;
  final int postCadenceMin;
  final int interactCadenceMin;
  final int qualityThreshold;
  final int dailyPostCap;
  final int dailyInteractCap;
  final int followers;
  final int following;
  final List<BotPostView> recentPosts;
  final List<BotCommentView> recentComments;

  factory BotDetail.fromJson(Map<String, dynamic> j) => BotDetail(
    id: j['id'] as String,
    handle: j['handle'] as String,
    displayName: j['display_name'] as String?,
    avatarUrl: j['avatar_url'] as String?,
    interests: _strList(j['interests']),
    tone: j['tone'] as String?,
    enabled: j['enabled'] as bool? ?? true,
    postsEnabled: j['posts_enabled'] as bool? ?? true,
    interactsEnabled: j['interacts_enabled'] as bool? ?? true,
    postsCount: (j['posts_count'] as num?)?.toInt() ?? 0,
    interactionsCount: (j['interactions_count'] as num?)?.toInt() ?? 0,
    lastPostAt: _dt(j['last_post_at']),
    lastInteractAt: _dt(j['last_interact_at']),
    persona: j['persona'] as String?,
    postCadenceMin: (j['post_cadence_min'] as num?)?.toInt() ?? 0,
    interactCadenceMin: (j['interact_cadence_min'] as num?)?.toInt() ?? 0,
    qualityThreshold: (j['quality_threshold'] as num?)?.toInt() ?? 0,
    dailyPostCap: (j['daily_post_cap'] as num?)?.toInt() ?? 0,
    dailyInteractCap: (j['daily_interact_cap'] as num?)?.toInt() ?? 0,
    followers: (j['followers'] as num?)?.toInt() ?? 0,
    following: (j['following'] as num?)?.toInt() ?? 0,
    recentPosts: (j['recent_posts'] as List? ?? const [])
        .map((e) => BotPostView.fromJson(e as Map<String, dynamic>))
        .toList(),
    recentComments: (j['recent_comments'] as List? ?? const [])
        .map((e) => BotCommentView.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

List<String> _strList(dynamic v) =>
    (v as List? ?? const []).map((e) => e.toString()).toList();

Map<String, int> _intMap(dynamic v) =>
    (v as Map? ?? const {}).map((k, val) => MapEntry(k as String, (val as num).toInt()));

DateTime? _dt(dynamic v) => v == null ? null : DateTime.tryParse(v as String)?.toLocal();

/// One open moderation flag in the admin approvals queue.
class ModerationFlag {
  ModerationFlag({
    required this.id,
    required this.targetType,
    required this.targetId,
    required this.source,
    required this.severity,
    required this.status,
    this.reason,
    this.preview,
    this.held = false,
    this.createdAt,
  });

  final String id;
  final String targetType;
  final String targetId;
  final String source;
  final int severity;
  final String status;
  final String? reason;
  final String? preview;
  final bool held;
  final DateTime? createdAt;

  factory ModerationFlag.fromJson(Map<String, dynamic> j) => ModerationFlag(
    id: j['id'] as String,
    targetType: j['target_type'] as String? ?? '',
    targetId: j['target_id'] as String? ?? '',
    source: j['source'] as String? ?? 'llm',
    severity: (j['severity'] as num?)?.toInt() ?? 0,
    status: j['status'] as String? ?? 'open',
    reason: j['reason'] as String?,
    preview: j['preview'] as String?,
    held: j['held'] as bool? ?? false,
    createdAt: _dt(j['created_at']),
  );
}

/// A page of the moderation queue + the total open count.
class ModerationQueue {
  ModerationQueue({required this.items, required this.count});
  final List<ModerationFlag> items;
  final int count;

  factory ModerationQueue.fromJson(Map<String, dynamic> j) => ModerationQueue(
    items: ((j['items'] as List?) ?? const [])
        .map((e) => ModerationFlag.fromJson(e as Map<String, dynamic>))
        .toList(),
    count: (j['count'] as num?)?.toInt() ?? 0,
  );
}
