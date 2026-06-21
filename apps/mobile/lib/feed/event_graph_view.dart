/// The event "graph / timeline web" reached by swiping **right** on a feed page (ADR-0027
/// §5). It lays the focused event and its one-hop related events out on a **horizontal time
/// axis** (past → future): each event is a node positioned by its `t_start`, the focused
/// event highlighted in the centre. Tapping a node opens that event (the host pushes a fresh
/// immersive feed/detail).
///
/// v1 keeps the layout deliberately simple — a time-sorted, lane-packed node list drawn with
/// connector lines via [CustomPaint] — rather than a force-directed graph. It draws on the
/// existing [ApiClient.related] data (same source the event article's "Related events"
/// footer uses); [ApiClient.chain] is available for a deeper causal walk in a later pass.
///
/// A button bridges to the classic map/timeline [ExperienceScreen] so nothing is lost when
/// the feed becomes the home (ADR-0027 keeps the experience reachable).
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import '../shell/experience_screen.dart';

/// Full-screen graph/timeline web for [root]. [onOpenEvent] is fired when a node is tapped.
class EventGraphView extends StatefulWidget {
  const EventGraphView({
    super.key,
    required this.api,
    required this.root,
    required this.onOpenEvent,
  });

  final ApiClient api;
  final EventRead root;
  final void Function(EventRead event) onOpenEvent;

  @override
  State<EventGraphView> createState() => _EventGraphViewState();
}

class _EventGraphViewState extends State<EventGraphView> {
  late Future<List<RelatedEvent>> _related;

  @override
  void initState() {
    super.initState();
    _related = widget.api
        .related(widget.root.id)
        .catchError((_) => <RelatedEvent>[]);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('History web'),
        actions: [
          IconButton(
            tooltip: 'Open the map & timeline',
            icon: const Icon(Icons.map_outlined),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const ExperienceScreen(),
              ),
            ),
          ),
        ],
      ),
      body: FutureBuilder<List<RelatedEvent>>(
        future: _related,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final related = snap.data ?? const <RelatedEvent>[];
          return GraphTimeline(
            root: widget.root,
            related: related,
            onOpenEvent: widget.onOpenEvent,
          );
        },
      ),
    );
  }
}

/// Pure layout widget: positions the root + related events on a horizontal time axis and
/// draws connectors from the root to each neighbour. Split out (and stateless) so it is
/// straightforward to widget-test with fixed data.
class GraphTimeline extends StatelessWidget {
  const GraphTimeline({
    super.key,
    required this.root,
    required this.related,
    required this.onOpenEvent,
  });

  final EventRead root;
  final List<RelatedEvent> related;
  final void Function(EventRead event) onOpenEvent;

  static const double _nodeWidth = 180;
  static const double _nodeHeight = 96;
  static const double _hGap = 24;
  static const double _rowHeight = 150;

  @override
  Widget build(BuildContext context) {
    // Build the time-ordered node list: root + neighbours, sorted past → future by t_start.
    final nodes = <_GraphNode>[
      _GraphNode(event: root, isRoot: true, kind: 'this event'),
      for (final r in related)
        _GraphNode(event: r.event, isRoot: false, kind: r.kind),
    ]..sort((a, b) => a.event.tStart.compareTo(b.event.tStart));

    final theme = Theme.of(context);
    // Lay nodes left→right in time order; root sits on the upper lane, neighbours on the
    // lower lane so connectors are visible. Width grows with node count → horizontal scroll.
    final totalWidth = nodes.length * (_nodeWidth + _hGap) + _hGap;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Icon(Icons.timeline, size: 18, color: theme.colorScheme.primary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Past → future · ${nodes.length} connected event'
                  '${nodes.length == 1 ? '' : 's'}',
                  style: theme.textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SizedBox(
              width: totalWidth,
              child: Stack(
                children: [
                  // Connector lines under the cards.
                  Positioned.fill(
                    child: CustomPaint(
                      painter: _ConnectorPainter(
                        count: nodes.length,
                        rootIndex: nodes.indexWhere((n) => n.isRoot),
                        nodeWidth: _nodeWidth,
                        hGap: _hGap,
                        rowHeight: _rowHeight,
                        nodeHeight: _nodeHeight,
                        color: theme.colorScheme.outline,
                      ),
                    ),
                  ),
                  for (var i = 0; i < nodes.length; i++)
                    Positioned(
                      left: _hGap + i * (_nodeWidth + _hGap),
                      top: nodes[i].isRoot ? 12 : _rowHeight - _nodeHeight + 12,
                      width: _nodeWidth,
                      height: _nodeHeight,
                      child: _NodeCard(
                        node: nodes[i],
                        onTap: () => onOpenEvent(nodes[i].event),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _GraphNode {
  _GraphNode({required this.event, required this.isRoot, required this.kind});
  final EventRead event;
  final bool isRoot;
  final String kind;
}

class _NodeCard extends StatelessWidget {
  const _NodeCard({required this.node, required this.onTap});
  final _GraphNode node;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final highlight = node.isRoot;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: highlight
              ? scheme.primaryContainer
              : scheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: highlight ? scheme.primary : scheme.outlineVariant,
            width: highlight ? 2 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              node.kind,
              style: theme.textTheme.labelSmall,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 4),
            Expanded(
              child: Text(
                node.event.title,
                style: theme.textTheme.bodySmall,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            Text(
              formatLabel(
                node.event.tStart,
                node.event.precision,
                instant: node.event.instant,
              ),
              style: theme.textTheme.labelSmall
                  ?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

/// Draws a connector from the root node down to each neighbour node.
class _ConnectorPainter extends CustomPainter {
  _ConnectorPainter({
    required this.count,
    required this.rootIndex,
    required this.nodeWidth,
    required this.hGap,
    required this.rowHeight,
    required this.nodeHeight,
    required this.color,
  });

  final int count;
  final int rootIndex;
  final double nodeWidth;
  final double hGap;
  final double rowHeight;
  final double nodeHeight;
  final Color color;

  Offset _center(int i, bool root) => Offset(
    hGap + i * (nodeWidth + hGap) + nodeWidth / 2,
    (root ? 12 : rowHeight - nodeHeight + 12) + nodeHeight / 2,
  );

  @override
  void paint(Canvas canvas, Size size) {
    if (rootIndex < 0) return;
    final paint = Paint()
      ..color = color.withValues(alpha: 0.6)
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;
    final rootPt = _center(rootIndex, true);
    for (var i = 0; i < count; i++) {
      if (i == rootIndex) continue;
      final pt = _center(i, false);
      final path = Path()
        ..moveTo(rootPt.dx, rootPt.dy)
        ..cubicTo(
          rootPt.dx,
          (rootPt.dy + pt.dy) / 2,
          pt.dx,
          (rootPt.dy + pt.dy) / 2,
          pt.dx,
          pt.dy,
        );
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(_ConnectorPainter old) =>
      old.count != count || old.rootIndex != rootIndex || old.color != color;
}
