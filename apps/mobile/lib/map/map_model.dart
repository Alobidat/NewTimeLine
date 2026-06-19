/// Fetches geolocated events for the current viewport bbox + shared time window
/// (debounced). Linked to the timeline via the same [TimeWindow].
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../state/time_window.dart';

class MapModel extends ChangeNotifier {
  MapModel({required this.window, ApiClient? api}) : _api = api ?? ApiClient() {
    window.addListener(_scheduleReload);
  }

  final TimeWindow window;
  final ApiClient _api;

  /// The shared API client, so detail/search/dig screens reuse one connection.
  ApiClient get api => _api;

  List<EventRead> events = const [];
  bool loading = false;
  String? error;

  String? _bbox; // last viewport bbox the map reported
  Timer? _debounce;

  /// Called by the map when the camera moves; triggers a debounced reload.
  void setBbox(String bbox) {
    if (bbox == _bbox) return;
    _bbox = bbox;
    _scheduleReload();
  }

  void _scheduleReload() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), reload);
  }

  Future<void> reload() async {
    final bbox = _bbox;
    if (bbox == null) return; // wait until the map reports its first viewport
    loading = true;
    error = null;
    notifyListeners();
    try {
      events = await _api.map(bbox: bbox, t0: window.t0, t1: window.t1);
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
    window.removeListener(_scheduleReload);
    _debounce?.cancel();
    _api.close();
    super.dispose();
  }
}
