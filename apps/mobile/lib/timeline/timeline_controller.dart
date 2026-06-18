/// Holds the timeline viewport (signed-year range) + fetched data, and reloads
/// (debounced) when the viewport changes.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/models.dart';

class TimelineController extends ChangeNotifier {
  TimelineController({ApiClient? api}) : _api = api ?? ApiClient();

  final ApiClient _api;

  // Default opening view: roughly the last century of news.
  double t0 = 1900;
  double t1 = 2030;

  TimelineResponse? data;
  bool loading = false;
  String? error;

  Timer? _debounce;

  /// Set the visible range now (for smooth repaint) and reload data shortly after.
  void setRange(double newT0, double newT1) {
    t0 = newT0;
    t1 = newT1;
    notifyListeners(); // repaint immediately with existing data at the new transform
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
    _debounce?.cancel();
    _api.close();
    super.dispose();
  }
}
