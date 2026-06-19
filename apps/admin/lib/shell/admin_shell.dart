/// Responsive admin shell — NavigationRail on wide screens (web/desktop), a bottom
/// NavigationBar on phones. One Flutter codebase serves web + apps (ADR-0002).
library;

import 'package:flutter/material.dart';

import '../api/admin_client.dart';
import '../screens/component_detail_screen.dart';
import '../screens/components_screen.dart';
import '../screens/config_screen.dart';
import '../screens/overview_screen.dart';
import '../screens/runs_screen.dart';
import '../screens/storage_screen.dart';
import '../screens/system_screen.dart';

class _Section {
  const _Section(this.label, this.icon);
  final String label;
  final IconData icon;
}

const _sections = [
  _Section('Overview', Icons.dashboard),
  _Section('Components', Icons.hub),
  _Section('Config', Icons.tune),
  _Section('Runs', Icons.history),
  _Section('Storage', Icons.save),
  _Section('System', Icons.memory),
];

class AdminShell extends StatefulWidget {
  const AdminShell({super.key});

  @override
  State<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends State<AdminShell> {
  final AdminClient _client = AdminClient();
  int _index = 0;

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  void _openComponent(String id) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ComponentDetailScreen(client: _client, componentId: id)),
    );
  }

  Widget _body() {
    switch (_index) {
      case 0:
        return OverviewScreen(client: _client, onOpenComponent: _openComponent);
      case 1:
        return ComponentsScreen(client: _client);
      case 2:
        return ConfigScreen(client: _client);
      case 3:
        return RunsScreen(client: _client);
      case 4:
        return StorageScreen(client: _client);
      default:
        return SystemScreen(client: _client);
    }
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 800;
    final title = 'Chronos Admin · ${_sections[_index].label}';

    if (wide) {
      return Scaffold(
        appBar: AppBar(title: Text(title)),
        body: Row(
          children: [
            NavigationRail(
              selectedIndex: _index,
              onDestinationSelected: (i) => setState(() => _index = i),
              labelType: NavigationRailLabelType.all,
              destinations: _sections
                  .map((s) => NavigationRailDestination(icon: Icon(s.icon), label: Text(s.label)))
                  .toList(),
            ),
            const VerticalDivider(width: 1),
            Expanded(child: _body()),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: _body(),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: _sections
            .map((s) => NavigationDestination(icon: Icon(s.icon), label: s.label))
            .toList(),
      ),
    );
  }
}
