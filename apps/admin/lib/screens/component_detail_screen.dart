/// One component in depth, as tabs: Overview (health/config/runs), Metrics (resource
/// time-series), and Logs (persisted WARNING+ records, container stdout tail, and runtime
/// log-level control).
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/config_tile.dart';
import '../widgets/health.dart';
import '../widgets/polling.dart';
import '../widgets/sparkline.dart';
import 'health_screen.dart' show formatMetric;
import 'runs_screen.dart' show RunTile;

class ComponentDetailScreen extends StatelessWidget {
  const ComponentDetailScreen({super.key, required this.client, required this.componentId});

  final AdminClient client;
  final String componentId;

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: Text(componentId),
          bottom: const TabBar(tabs: [
            Tab(text: 'Overview', icon: Icon(Icons.info_outline)),
            Tab(text: 'Metrics', icon: Icon(Icons.show_chart)),
            Tab(text: 'Logs', icon: Icon(Icons.article_outlined)),
          ]),
        ),
        body: TabBarView(children: [
          _OverviewTab(client: client, componentId: componentId),
          _MetricsTab(client: client, componentId: componentId),
          _LogsTab(client: client, componentId: componentId),
        ]),
      ),
    );
  }
}

// ── Overview tab ─────────────────────────────────────────────────────────────────────────

class _OverviewTab extends StatefulWidget {
  const _OverviewTab({required this.client, required this.componentId});
  final AdminClient client;
  final String componentId;

  @override
  State<_OverviewTab> createState() => _OverviewTabState();
}

class _OverviewTabState extends State<_OverviewTab> {
  int _reload = 0;

  Future<void> _action(String action) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.client.action(widget.componentId, action);
      messenger.showSnackBar(SnackBar(content: Text('$action ok')));
      setState(() => _reload++);
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Failed: $msg')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<ComponentDetail>(
      key: ValueKey(_reload),
      interval: AdminConfig.pollInterval,
      fetch: () => widget.client.component(widget.componentId),
      builder: (context, c) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              Expanded(child: Text(c.title, style: Theme.of(context).textTheme.headlineSmall)),
              if (c.health.level != 'ok') ...[LevelBadge(level: c.health.level), const SizedBox(width: 8)],
              StatusChip(status: c.health.status),
            ],
          ),
          const SizedBox(height: 8),
          Text(c.description),
          if (c.health.message != null) ...[
            const SizedBox(height: 8),
            Text(c.health.message!, style: TextStyle(color: levelColor(c.health.level))),
          ],
          const SizedBox(height: 12),
          _healthLine(context, c.health),
          if (c.capabilities.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: c.capabilities.map((cap) => Chip(label: Text(cap))).toList(),
            ),
          ],
          if (c.actions.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(spacing: 8, children: c.actions.map(_actionButton).toList()),
          ],
          if (c.config.isNotEmpty) ...[
            const Divider(height: 32),
            Text('Configuration', style: Theme.of(context).textTheme.titleMedium),
            ...c.config.map((e) => ConfigTile(
                  entry: e,
                  client: widget.client,
                  onChanged: () => setState(() => _reload++),
                )),
          ],
          const Divider(height: 32),
          Text('Recent runs', style: Theme.of(context).textTheme.titleMedium),
          if (c.recentRuns.isEmpty)
            const Padding(padding: EdgeInsets.all(8), child: Text('No runs yet.'))
          else
            ...c.recentRuns.map((r) => RunTile(run: r)),
        ],
      ),
    );
  }

  Widget _actionButton(String action) {
    final enable = action == 'enable';
    final disable = action == 'disable';
    return FilledButton.tonalIcon(
      onPressed: () => _action(action),
      icon: Icon(enable
          ? Icons.play_arrow
          : disable
              ? Icons.pause
              : Icons.bolt),
      label: Text(action),
    );
  }

  Widget _healthLine(BuildContext context, HealthView h) {
    final parts = <String>[
      'runs: ${h.runs}',
      if (h.successRate != null) 'success: ${(h.successRate! * 100).round()}%',
      if (h.lastRunAt != null) 'last: ${h.lastRunAt!.toLocal()}',
    ];
    return Text(parts.join('   ·   '), style: Theme.of(context).textTheme.bodySmall);
  }
}

// ── Metrics tab ──────────────────────────────────────────────────────────────────────────

class _MetricsTab extends StatefulWidget {
  const _MetricsTab({required this.client, required this.componentId});
  final AdminClient client;
  final String componentId;

  @override
  State<_MetricsTab> createState() => _MetricsTabState();
}

class _MetricsTabState extends State<_MetricsTab> {
  static const _windows = {'1h': 3600, '6h': 21600, '24h': 86400};
  String _window = '1h';
  int _reload = 0;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Row(
            children: [
              Text('Window', style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(width: 8),
              SegmentedButton<String>(
                segments: _windows.keys
                    .map((w) => ButtonSegment(value: w, label: Text(w)))
                    .toList(),
                selected: {_window},
                onSelectionChanged: (s) => setState(() {
                  _window = s.first;
                  _reload++;
                }),
              ),
            ],
          ),
        ),
        Expanded(
          child: PollingBuilder<List<MetricSeries>>(
            key: ValueKey(_reload),
            interval: const Duration(seconds: 5),
            fetch: () =>
                widget.client.componentMetrics(widget.componentId, window: _windows[_window]!),
            builder: (context, series) {
              if (series.isEmpty) {
                return Center(child: Text('No resource samples in the last $_window.'));
              }
              series.sort((a, b) => a.metric.compareTo(b.metric));
              return ListView(
                padding: const EdgeInsets.all(16),
                children: [for (final s in series) _MetricCard(series: s)],
              );
            },
          ),
        ),
      ],
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.series});
  final MetricSeries series;

  @override
  Widget build(BuildContext context) {
    final values = series.points.map((p) => p.value).toList();
    final latest = values.isEmpty ? null : values.last;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(series.metric, style: const TextStyle(fontWeight: FontWeight.w700)),
                const Spacer(),
                if (latest != null)
                  Text(formatMetric(series.metric, latest),
                      style: const TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF2E7DF6))),
              ],
            ),
            const SizedBox(height: 8),
            Sparkline(values: values),
          ],
        ),
      ),
    );
  }
}

// ── Logs tab ─────────────────────────────────────────────────────────────────────────────

class _LogsTab extends StatefulWidget {
  const _LogsTab({required this.client, required this.componentId});
  final AdminClient client;
  final String componentId;

  @override
  State<_LogsTab> createState() => _LogsTabState();
}

class _LogsTabState extends State<_LogsTab> {
  String? _level; // null = all
  String _query = '';
  int _reload = 0;
  LogLevelView? _logLevel;
  final _searchCtl = TextEditingController();

  @override
  void initState() {
    super.initState();
    widget.client.logLevel(widget.componentId).then((v) {
      if (mounted) setState(() => _logLevel = v);
    }).catchError((_) {});
  }

  @override
  void dispose() {
    _searchCtl.dispose();
    super.dispose();
  }

  Future<void> _setLevel(String level) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final v = await widget.client.setLogLevel(widget.componentId, level);
      if (mounted) setState(() => _logLevel = v);
      messenger.showSnackBar(SnackBar(content: Text('Log level → $level')));
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Failed: $msg')));
    }
  }

  Future<void> _tail() async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final text = await widget.client.logsTail(widget.componentId, tail: 300);
      if (!mounted) return;
      showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        builder: (_) => _TailSheet(componentId: widget.componentId, text: text),
      );
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Tail unavailable: $msg')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final ll = _logLevel;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              if (ll != null && ll.controllable)
                _LevelControl(level: ll.level, choices: ll.choices, onChanged: _setLevel)
              else if (ll != null && ll.note != null)
                Text(ll.note!, style: Theme.of(context).textTheme.bodySmall),
              DropdownButton<String?>(
                value: _level,
                hint: const Text('All levels'),
                items: const [
                  DropdownMenuItem(value: null, child: Text('All levels')),
                  DropdownMenuItem(value: 'WARNING', child: Text('WARNING')),
                  DropdownMenuItem(value: 'ERROR', child: Text('ERROR')),
                  DropdownMenuItem(value: 'CRITICAL', child: Text('CRITICAL')),
                ],
                onChanged: (v) => setState(() {
                  _level = v;
                  _reload++;
                }),
              ),
              SizedBox(
                width: 200,
                child: TextField(
                  controller: _searchCtl,
                  decoration: const InputDecoration(
                    isDense: true,
                    prefixIcon: Icon(Icons.search, size: 18),
                    hintText: 'search message',
                  ),
                  onSubmitted: (v) => setState(() {
                    _query = v;
                    _reload++;
                  }),
                ),
              ),
              OutlinedButton.icon(
                onPressed: _tail,
                icon: const Icon(Icons.terminal, size: 18),
                label: const Text('Tail stdout'),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: PollingBuilder<List<LogRecordView>>(
            key: ValueKey(_reload),
            interval: const Duration(seconds: 5),
            fetch: () => widget.client.componentLogs(
              widget.componentId,
              level: _level,
              q: _query.isEmpty ? null : _query,
              limit: 200,
            ),
            builder: (context, logs) {
              if (logs.isEmpty) {
                return const Center(child: Text('No warning/error logs recorded.'));
              }
              return ListView.separated(
                padding: const EdgeInsets.all(8),
                itemCount: logs.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (_, i) => _LogTile(record: logs[i]),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _LevelControl extends StatelessWidget {
  const _LevelControl({required this.level, required this.choices, required this.onChanged});
  final String? level;
  final List<String> choices;
  final void Function(String) onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.tune, size: 16),
        const SizedBox(width: 6),
        const Text('Log level', style: TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(width: 8),
        DropdownButton<String>(
          value: choices.contains(level) ? level : null,
          items: choices.map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
          onChanged: (v) => v == null ? null : onChanged(v),
        ),
      ],
    );
  }
}

class _LogTile extends StatelessWidget {
  const _LogTile({required this.record});
  final LogRecordView record;

  Color get _color => switch (record.level) {
        'ERROR' || 'CRITICAL' => const Color(0xFFE5534B),
        'WARNING' => const Color(0xFFD29922),
        _ => const Color(0xFF8B949E),
      };

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: _color.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(record.level,
                    style: TextStyle(color: _color, fontWeight: FontWeight.w700, fontSize: 11)),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(record.logger,
                    style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis),
              ),
              Text('${record.ts.toLocal()}'.split('.').first,
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
          const SizedBox(height: 4),
          SelectableText(record.message,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
        ],
      ),
    );
  }
}

class _TailSheet extends StatelessWidget {
  const _TailSheet({required this.componentId, required this.text});
  final String componentId;
  final String text;

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.7,
      maxChildSize: 0.95,
      builder: (context, scroll) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                const Icon(Icons.terminal, size: 18),
                const SizedBox(width: 8),
                Text('$componentId · stdout tail',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                const Spacer(),
                IconButton(
                    onPressed: () => Navigator.of(context).pop(), icon: const Icon(Icons.close)),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: SingleChildScrollView(
              controller: scroll,
              padding: const EdgeInsets.all(12),
              child: SelectableText(
                text.isEmpty ? '(no output)' : text,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
