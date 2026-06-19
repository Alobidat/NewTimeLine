/// All runtime config, grouped by scope — schema-driven forms (ADR-0019).
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../widgets/config_tile.dart';
import '../widgets/polling.dart';

class ConfigScreen extends StatefulWidget {
  const ConfigScreen({super.key, required this.client});
  final AdminClient client;

  @override
  State<ConfigScreen> createState() => _ConfigScreenState();
}

class _ConfigScreenState extends State<ConfigScreen> {
  int _reload = 0;

  @override
  Widget build(BuildContext context) {
    return PollingBuilder<List<ConfigEntry>>(
      key: ValueKey(_reload),
      interval: AdminConfig.pollInterval,
      fetch: () => widget.client.config(),
      builder: (context, entries) {
        final scopes = <String, List<ConfigEntry>>{};
        for (final e in entries) {
          scopes.putIfAbsent(e.scope, () => []).add(e);
        }
        final ordered = scopes.keys.toList()..sort();
        return ListView(
          padding: const EdgeInsets.all(8),
          children: [
            for (final scope in ordered)
              Card(
                child: ExpansionTile(
                  title: Text(scope, style: const TextStyle(fontWeight: FontWeight.w600)),
                  initiallyExpanded: true,
                  children: scopes[scope]!
                      .map((e) => ConfigTile(
                            entry: e,
                            client: widget.client,
                            onChanged: () => setState(() => _reload++),
                          ))
                      .toList(),
                ),
              ),
          ],
        );
      },
    );
  }
}
