/// Fetches timeline data for the shared [TimeWindow] (debounced) and notifies the view.
/// The window is shared with the map so the two surfaces stay linked.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../state/time_window.dart';

class TimelineController extends ChangeNotifier {
  TimelineController({required this.window, ApiClient? api})
    : _api = api ?? ApiClient() {
    window.addListener(_onWindowChanged);
  }

  final TimeWindow window;
  final ApiClient _api;

  TimelineResponse? data;
  bool loading = false;
  String? error;
  Timer? _debounce;

  double get t0 => window.t0;
  double get t1 => window.t1;

  /// Update the shared window (repaints both surfaces; reloads shortly after).
  void setRange(double newT0, double newT1) => window.set(newT0, newT1);

  void _onWindowChanged() {
    notifyListeners(); // repaint immediately at the new transform
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 250), reload);
  }

  Future<void> reload() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      data = await _api.timeline(t0: t0, t1: t1);
    } catch (e) {
      error = e.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<EventDetail> fetchDetail(String id) => _api.event(id);

  @override
  void dispose() {
    window.removeListener(_onWindowChanged);
    _debounce?.cancel();
    _api.close();
    super.dispose();
  }
}
