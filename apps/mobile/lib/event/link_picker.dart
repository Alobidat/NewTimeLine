/// "Link this event" affordance (ADR-0025 §2.4). Opens a dialog where the user searches
/// for a target event, picks one, chooses a relation [kind] (default `thematic`), and the
/// dialog calls `POST /links`. On success the host reloads `/related`; the new edge comes
/// back tagged `origin=user` and renders distinctly in the related footer.
///
/// Search reuses the existing `/search` endpoint (events facet); the picker does not
/// trigger live collection (collect=false) — it only links to events that already exist.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';

/// Relation kinds a user may assert. `thematic` is the default per ADR-0025.
const List<String> kUserLinkKinds = [
  'thematic',
  'precursor',
  'consequence',
  'same-place',
  'same-actor',
];

/// Open the link picker for [srcEventId]. Returns true if a link was created (so the host
/// can reload its related footer).
Future<bool> showLinkPicker(
  BuildContext context,
  ApiClient api, {
  required String srcEventId,
}) async {
  final created = await showDialog<bool>(
    context: context,
    builder: (_) => _LinkPickerDialog(api: api, srcEventId: srcEventId),
  );
  return created ?? false;
}

class _LinkPickerDialog extends StatefulWidget {
  const _LinkPickerDialog({required this.api, required this.srcEventId});
  final ApiClient api;
  final String srcEventId;

  @override
  State<_LinkPickerDialog> createState() => _LinkPickerDialogState();
}

class _LinkPickerDialogState extends State<_LinkPickerDialog> {
  final _ctrl = TextEditingController();
  Timer? _debounce;
  List<EventRead> _results = const [];
  bool _searching = false;
  EventRead? _selected;
  String _kind = kUserLinkKinds.first;
  bool _saving = false;

  @override
  void dispose() {
    _debounce?.cancel();
    _ctrl.dispose();
    super.dispose();
  }

  void _onQueryChanged(String q) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _search(q));
  }

  Future<void> _search(String q) async {
    final query = q.trim();
    if (query.isEmpty) {
      setState(() {
        _results = const [];
        _searching = false;
      });
      return;
    }
    setState(() => _searching = true);
    try {
      final res = await widget.api.search(q: query, collect: false, limit: 20);
      if (!mounted) return;
      setState(() {
        // Don't offer to link an event to itself.
        _results =
            res.events.where((e) => e.id != widget.srcEventId).toList();
      });
    } catch (_) {
      if (mounted) setState(() => _results = const []);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _save() async {
    final target = _selected;
    if (target == null || _saving) return;
    setState(() => _saving = true);
    try {
      await widget.api
          .createLink(widget.srcEventId, target.id, kind: _kind);
      if (mounted) Navigator.pop(context, true);
    } catch (_) {
      if (mounted) {
        setState(() => _saving = false);
        ScaffoldMessenger.maybeOf(context)?.showSnackBar(
          const SnackBar(content: Text('Could not create the link.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Link to another event'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _ctrl,
              autofocus: true,
              decoration: InputDecoration(
                hintText: 'Search for an event…',
                isDense: true,
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searching
                    ? const Padding(
                        padding: EdgeInsets.all(12),
                        child: SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    : null,
                border: const OutlineInputBorder(),
              ),
              onChanged: _onQueryChanged,
            ),
            const SizedBox(height: 8),
            if (_selected != null) ...[
              _SelectedRow(
                event: _selected!,
                onClear: () => setState(() => _selected = null),
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                initialValue: _kind,
                decoration: const InputDecoration(
                  labelText: 'Relation',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
                items: [
                  for (final k in kUserLinkKinds)
                    DropdownMenuItem(value: k, child: Text(k)),
                ],
                onChanged: (v) => setState(() => _kind = v ?? _kind),
              ),
            ] else
              SizedBox(
                height: 240,
                child: _results.isEmpty
                    ? Center(
                        child: Text(
                          _ctrl.text.trim().isEmpty
                              ? 'Type to search for an event to link.'
                              : 'No matching events.',
                          style: theme.textTheme.bodySmall,
                        ),
                      )
                    : ListView.builder(
                        shrinkWrap: true,
                        itemCount: _results.length,
                        itemBuilder: (_, i) {
                          final e = _results[i];
                          return ListTile(
                            key: Key('link-result-${e.id}'),
                            dense: true,
                            contentPadding: EdgeInsets.zero,
                            title: Text(e.title,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis),
                            subtitle: Text(formatLabel(e.tStart, e.precision,
                                instant: e.instant)),
                            onTap: () => setState(() => _selected = e),
                          );
                        },
                      ),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.pop(context, false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _selected == null || _saving ? null : _save,
          child: const Text('Create link'),
        ),
      ],
    );
  }
}

class _SelectedRow extends StatelessWidget {
  const _SelectedRow({required this.event, required this.onClear});
  final EventRead event;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          const Icon(Icons.link, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(event.title,
                maxLines: 2, overflow: TextOverflow.ellipsis),
          ),
          IconButton(
            icon: const Icon(Icons.close, size: 18),
            visualDensity: VisualDensity.compact,
            onPressed: onClear,
          ),
        ],
      ),
    );
  }
}
