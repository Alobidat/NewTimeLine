/// The shared visible time range (signed years), so the timeline and map stay linked:
/// scrubbing one updates the other. Consumers debounce their own data reloads.
library;

import 'package:flutter/foundation.dart';

class TimeWindow extends ChangeNotifier {
  TimeWindow({this.t0 = 1900, this.t1 = 2030});

  double t0;
  double t1;

  void set(double newT0, double newT1) {
    if (newT0 == t0 && newT1 == t1) return;
    t0 = newT0;
    t1 = newT1;
    notifyListeners();
  }
}
