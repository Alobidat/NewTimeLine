/// Fetches the bandwidth-safe [TimelineSummary] for the shared [TimeWindow] (debounced).
/// This is the "many events → one view" feed: it powers both the summary panel montage and
/// the set of countries the silhouette map draws. Keyed on the time window only, so the
/// payload stays bounded no matter how dense the window is (the server does the collapsing).
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../state/time_window.dart';

class SummaryModel extends ChangeNotifier {
  SummaryModel({required this.window, required ApiClient api}) : _api = api {
    window.addListener(_schedule);
  }

  final TimeWindow window;
  final ApiClient _api;

  TimelineSummary? summary;
  bool loading = false;
  String? error;
  Timer? _debounce;

  void _schedule() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), reload);
  }

  Future<void> reload() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      summary = await _api.timelineSummary(t0: window.t0, t1: window.t1);
    } catch (e) {
      error = e.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    window.removeListener(_schedule);
    _debounce?.cancel();
    super.dispose();
  }
}
