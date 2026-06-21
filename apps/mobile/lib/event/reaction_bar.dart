/// The reaction bar (ADR-0025 §2.2): like / dislike / important / doubt with live counts.
/// Tapping a reaction toggles it and updates the count **optimistically** — the chip flips
/// active and the count nudges immediately — then reconciles to the fresh aggregate the
/// server returns. A failed toggle rolls back to the last known-good summary.
///
/// Sits near the title/meta in [EventArticle]. Writes go through the identity stub, so no
/// user id is sent; auth lands in Phase 4 with no change here.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';

/// Display metadata per reaction kind.
const Map<String, ({IconData icon, IconData iconActive, String label})>
kReactionKinds = {
  'like': (
    icon: Icons.thumb_up_outlined,
    iconActive: Icons.thumb_up,
    label: 'Like',
  ),
  'dislike': (
    icon: Icons.thumb_down_outlined,
    iconActive: Icons.thumb_down,
    label: 'Dislike',
  ),
  'important': (
    icon: Icons.star_border,
    iconActive: Icons.star,
    label: 'Important',
  ),
  'doubt': (
    icon: Icons.help_outline,
    iconActive: Icons.help,
    label: 'Doubt',
  ),
};

class ReactionBar extends StatefulWidget {
  const ReactionBar({super.key, required this.api, required this.eventId});

  final ApiClient api;
  final String eventId;

  @override
  State<ReactionBar> createState() => _ReactionBarState();
}

class _ReactionBarState extends State<ReactionBar> {
  ReactionSummary? _summary;
  bool _loaded = false;
  final Set<String> _inFlight = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(ReactionBar old) {
    super.didUpdateWidget(old);
    if (old.eventId != widget.eventId) {
      _summary = null;
      _loaded = false;
      _load();
    }
  }

  Future<void> _load() async {
    try {
      final s = await widget.api.reactions(widget.eventId);
      if (mounted) setState(() => _summary = s);
    } catch (_) {
      // Leave counts at zero on failure; the bar still renders + toggles can retry.
    } finally {
      if (mounted) setState(() => _loaded = true);
    }
  }

  /// Optimistic toggle: flip the kind and nudge its count now, then reconcile with the
  /// server's authoritative aggregate (or roll back on error).
  Future<void> _toggle(String kind) async {
    if (_inFlight.contains(kind)) return;
    final before = _summary;
    final wasMine = before?.isMine(kind) ?? false;
    final baseCount = before?.countOf(kind) ?? 0;

    setState(() {
      _inFlight.add(kind);
      _summary = _optimistic(before, kind, !wasMine, baseCount);
    });

    try {
      final fresh = await widget.api.toggleReaction(widget.eventId, kind);
      if (mounted) setState(() => _summary = fresh);
    } catch (_) {
      if (mounted) {
        setState(() => _summary = before); // roll back
        ScaffoldMessenger.maybeOf(context)?.showSnackBar(
          const SnackBar(content: Text('Could not save your reaction.')),
        );
      }
    } finally {
      if (mounted) setState(() => _inFlight.remove(kind));
    }
  }

  ReactionSummary _optimistic(
    ReactionSummary? base,
    String kind,
    bool active,
    int baseCount,
  ) {
    final counts = Map<String, int>.from(base?.counts ?? const {});
    final mine = Set<String>.from(base?.mine ?? const <String>{});
    counts[kind] = (baseCount + (active ? 1 : -1)).clamp(0, 1 << 30);
    if (active) {
      mine.add(kind);
    } else {
      mine.remove(kind);
    }
    return ReactionSummary(eventId: widget.eventId, counts: counts, mine: mine);
  }

  @override
  Widget build(BuildContext context) {
    final s = _summary;
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final kind in ReactionSummary.kinds)
          _ReactionChip(
            kind: kind,
            count: s?.countOf(kind) ?? 0,
            active: s?.isMine(kind) ?? false,
            busy: _inFlight.contains(kind),
            enabled: _loaded,
            onTap: () => _toggle(kind),
          ),
      ],
    );
  }
}

class _ReactionChip extends StatelessWidget {
  const _ReactionChip({
    required this.kind,
    required this.count,
    required this.active,
    required this.busy,
    required this.enabled,
    required this.onTap,
  });

  final String kind;
  final int count;
  final bool active;
  final bool busy;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final meta = kReactionKinds[kind]!;
    final selectedColor = theme.colorScheme.primary;
    return FilterChip(
      key: Key('reaction-$kind'),
      selected: active,
      showCheckmark: false,
      visualDensity: VisualDensity.compact,
      avatar: Icon(
        active ? meta.iconActive : meta.icon,
        size: 16,
        color: active ? selectedColor : null,
      ),
      label: Text(count > 0 ? '${meta.label}  $count' : meta.label),
      onSelected: enabled && !busy ? (_) => onTap() : null,
    );
  }
}
