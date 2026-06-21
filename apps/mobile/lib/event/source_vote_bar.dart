/// Per-source credibility voting (ADR-0025 §2.3): corroborate / dispute / irrelevant with
/// running tallies. Rendered under each source row in [EventArticle]. The bar is fed the
/// shared [SourceVotes] aggregate (one fetch per event) and reports the verdict it casts so
/// the parent can refresh tallies from the server's response.
library;

import 'package:flutter/material.dart';

import '../api/models.dart';

/// Display metadata per verdict.
const Map<String, ({IconData icon, String label})> kVerdicts = {
  'corroborate': (icon: Icons.check_circle_outline, label: 'Corroborate'),
  'dispute': (icon: Icons.report_gmailerrorred_outlined, label: 'Dispute'),
  'irrelevant': (icon: Icons.block_outlined, label: 'Irrelevant'),
};

class SourceVoteBar extends StatelessWidget {
  const SourceVoteBar({
    super.key,
    required this.sourceId,
    required this.votes,
    required this.busy,
    required this.onCast,
  });

  final String sourceId;

  /// Shared aggregate for the whole event (null while still loading).
  final SourceVotes? votes;
  final bool busy;
  final Future<void> Function(String verdict) onCast;

  @override
  Widget build(BuildContext context) {
    final tallies = votes?.talliesFor(sourceId) ?? const {};
    final mine = votes?.mineFor(sourceId);
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final verdict in SourceVotes.verdicts)
          _VerdictChip(
            verdict: verdict,
            count: tallies[verdict] ?? 0,
            active: mine == verdict,
            enabled: votes != null && !busy,
            onTap: () => onCast(verdict),
          ),
      ],
    );
  }
}

class _VerdictChip extends StatelessWidget {
  const _VerdictChip({
    required this.verdict,
    required this.count,
    required this.active,
    required this.enabled,
    required this.onTap,
  });

  final String verdict;
  final int count;
  final bool active;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final meta = kVerdicts[verdict]!;
    return FilterChip(
      key: Key('vote-$verdict'),
      selected: active,
      showCheckmark: false,
      visualDensity: VisualDensity.compact,
      avatar: Icon(meta.icon, size: 15),
      label: Text(count > 0 ? '${meta.label}  $count' : meta.label),
      onSelected: enabled ? (_) => onTap() : null,
    );
  }
}
