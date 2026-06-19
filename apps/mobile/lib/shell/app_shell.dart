/// The linked surfaces: map on top, timeline below, sharing one [TimeWindow] so scrubbing
/// time updates the map and panning the map refilters by the visible time range.
library;

import 'package:flutter/material.dart';

import '../map/map_model.dart';
import '../map/map_view.dart';
import '../search/search_screen.dart';
import '../state/time_window.dart';
import '../timeline/timeline_controller.dart';
import '../timeline/timeline_panel.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final TimeWindow _window = TimeWindow();
  late final TimelineController _timeline = TimelineController(window: _window);
  late final MapModel _map = MapModel(window: _window);

  @override
  void initState() {
    super.initState();
    _timeline.reload(); // map reloads once it reports its first viewport
  }

  @override
  void dispose() {
    _timeline.dispose();
    _map.dispose();
    _window.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Chronos — Timeline'),
        actions: [
          IconButton(
            tooltip: 'Search & dig',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => SearchScreen(api: _timeline.api)),
            ),
            icon: const Icon(Icons.search),
          ),
          IconButton(
            tooltip: 'Reload',
            onPressed: () {
              _timeline.reload();
              _map.reload();
            },
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(flex: 3, child: MapView(model: _map)),
          const Divider(height: 1),
          // Fixed-height timeline strip beneath the map.
          SizedBox(height: 220, child: TimelinePanel(controller: _timeline)),
        ],
      ),
    );
  }
}
