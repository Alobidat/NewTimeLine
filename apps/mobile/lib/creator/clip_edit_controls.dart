/// Inline trim + speed controls for a chosen clip (Creator Studio Phase 1 — the "edit" step).
///
/// A thin, stateless view over a [ClipProject]: it renders speed chips (always) and a trim range
/// slider (only when the clip's duration is known, e.g. an in-app recording), and reports edits
/// back through [onChanged]. All edit logic/validation lives in the pure [ClipProject]; this is
/// just the surface. The host (`UploadScreen`) owns the project and forwards its upload params.
library;

import 'package:flutter/material.dart';

import 'clip_project.dart';

class ClipEditControls extends StatelessWidget {
  const ClipEditControls({super.key, required this.project, required this.onChanged});

  final ClipProject project;
  final ValueChanged<ClipProject> onChanged;

  /// The speeds we offer — the range ffmpeg's atempo handles in one pass (see [ClipProject]).
  static const List<double> speeds = [0.5, 1.0, 2.0];

  static String _label(double s) => s == s.roundToDouble() ? '${s.toInt()}×' : '$s×';

  static String _time(double seconds) {
    final s = seconds.round();
    final m = (s ~/ 60).toString().padLeft(2, '0');
    final r = (s % 60).toString().padLeft(2, '0');
    return '$m:$r';
  }

  @override
  Widget build(BuildContext context) {
    final effectiveSpeed = project.uploadSpeed ?? 1.0;
    final dur = project.durationS ?? 0;
    final start = project.trimStart ?? 0;
    final end = project.trimEnd ?? dur;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 12),
        Row(
          children: [
            const Icon(Icons.speed, size: 18),
            const SizedBox(width: 8),
            const Text('Speed', style: TextStyle(fontWeight: FontWeight.w600)),
            const Spacer(),
            for (final s in speeds)
              Padding(
                padding: const EdgeInsets.only(left: 6),
                child: ChoiceChip(
                  key: Key('clip-speed-$s'),
                  label: Text(_label(s)),
                  selected: effectiveSpeed == s,
                  onSelected: (_) => onChanged(project.copyWith(speed: s)),
                ),
              ),
          ],
        ),
        if (project.canTrim) ...[
          const SizedBox(height: 4),
          Row(
            children: [
              const Icon(Icons.content_cut, size: 18),
              const SizedBox(width: 8),
              const Text('Trim', style: TextStyle(fontWeight: FontWeight.w600)),
              const Spacer(),
              Text('${_time(start)} – ${_time(end)}',
                  key: const Key('clip-trim-label'),
                  style: TextStyle(color: Colors.grey.shade600)),
            ],
          ),
          RangeSlider(
            key: const Key('clip-trim'),
            min: 0,
            max: dur,
            divisions: dur >= 1 ? dur.round() : null,
            values: RangeValues(start.clamp(0, dur).toDouble(), end.clamp(0, dur).toDouble()),
            labels: RangeLabels(_time(start), _time(end)),
            onChanged: (v) {
              // Snap the handles back to "no bound" when they sit at the clip's edges, so an
              // untouched trim sends nothing (mirrors the pure model's normalization).
              final atStart = v.start <= 0.001;
              final atEnd = v.end >= dur - 0.001;
              onChanged(project.copyWith(
                trimStart: atStart ? null : v.start,
                clearTrimStart: atStart,
                trimEnd: atEnd ? null : v.end,
                clearTrimEnd: atEnd,
              ));
            },
          ),
        ],
      ],
    );
  }
}
