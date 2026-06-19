/// A schema-driven config row: renders + edits one [ConfigEntry] according to its declared
/// type (bool → switch, numbers/strings/enums → dialogs, list/json → JSON editor). The form
/// is generated entirely from the spec the Admin API returns (ADR-0019).
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';

class ConfigTile extends StatelessWidget {
  const ConfigTile({super.key, required this.entry, required this.client, required this.onChanged});

  final ConfigEntry entry;
  final AdminClient client;
  final VoidCallback onChanged;

  Future<void> _save(BuildContext context, dynamic value) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await client.setConfig(entry.key, value);
      onChanged();
      messenger.showSnackBar(SnackBar(content: Text('Updated ${entry.key}')));
    } catch (e) {
      final msg = e is ApiException ? e.message : e.toString();
      messenger.showSnackBar(SnackBar(content: Text('Update failed: $msg')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final subtitle = [
      if (entry.help.isNotEmpty) entry.help,
      entry.key,
    ].join('\n');

    if (entry.type == 'bool') {
      return SwitchListTile(
        title: Text(entry.label),
        subtitle: Text(subtitle),
        isThreeLine: entry.help.isNotEmpty,
        value: entry.value == true,
        onChanged: entry.secret ? null : (v) => _save(context, v),
      );
    }

    return ListTile(
      title: Text(entry.label),
      subtitle: Text(subtitle),
      isThreeLine: entry.help.isNotEmpty,
      trailing: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 200),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: Text(
                _preview(entry.value),
                textAlign: TextAlign.end,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontFamily: 'monospace'),
              ),
            ),
            IconButton(
              icon: const Icon(Icons.edit, size: 18),
              tooltip: entry.secret ? 'Secret — managed elsewhere' : 'Edit',
              onPressed: entry.secret ? null : () => _edit(context),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _edit(BuildContext context) async {
    if (entry.type == 'enum' && entry.choices != null) {
      final picked = await showDialog<String>(
        context: context,
        builder: (ctx) => SimpleDialog(
          title: Text(entry.label),
          children: entry.choices!
              .map((c) => SimpleDialogOption(
                    onPressed: () => Navigator.pop(ctx, c),
                    child: Text(c),
                  ))
              .toList(),
        ),
      );
      if (picked != null && context.mounted) await _save(context, picked);
      return;
    }

    final isJson = entry.type == 'list' || entry.type == 'json';
    final initial = isJson
        ? const JsonEncoder.withIndent('  ').convert(entry.value)
        : '${entry.value ?? ''}';
    final controller = TextEditingController(text: initial);
    final hint = switch (entry.type) {
      'int' || 'float' => 'number'
          '${entry.minimum != null ? ' ≥ ${entry.minimum}' : ''}'
          '${entry.maximum != null ? ' ≤ ${entry.maximum}' : ''}',
      'list' || 'json' => 'JSON',
      _ => 'text',
    };

    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(entry.label),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: isJson ? 10 : 1,
          keyboardType: entry.type == 'int' || entry.type == 'float'
              ? TextInputType.number
              : TextInputType.text,
          decoration: InputDecoration(helperText: hint, border: const OutlineInputBorder()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, controller.text), child: const Text('Save')),
        ],
      ),
    );
    if (result == null) return;

    dynamic parsed;
    try {
      parsed = switch (entry.type) {
        'int' => int.parse(result.trim()),
        'float' => double.parse(result.trim()),
        'list' || 'json' => jsonDecode(result),
        _ => result,
      };
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Invalid value for this field')));
      }
      return;
    }
    if (context.mounted) await _save(context, parsed);
  }

  static String _preview(dynamic value) {
    if (value == null) return '—';
    if (value is Map || value is List) return jsonEncode(value);
    return value.toString();
  }
}
