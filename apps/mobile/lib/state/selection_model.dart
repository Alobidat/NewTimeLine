/// Which event (if any) is in focus. Null → the timeframe **summary** is shown (many events
/// collapsed into one view); a selected id → the **detail** of that one event. Selecting or
/// clearing drives both the morphing panel and the animated camera in the Experience screen.
library;

import 'package:flutter/foundation.dart';

enum ViewMode { summary, detail }

class SelectionModel extends ChangeNotifier {
  String? _selectedId;

  String? get selectedEventId => _selectedId;
  ViewMode get mode => _selectedId == null ? ViewMode.summary : ViewMode.detail;

  void select(String id) {
    if (_selectedId == id) return;
    _selectedId = id;
    notifyListeners();
  }

  void clear() {
    if (_selectedId == null) return;
    _selectedId = null;
    notifyListeners();
  }
}
