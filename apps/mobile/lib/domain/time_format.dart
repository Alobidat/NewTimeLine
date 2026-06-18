/// Precision-aware formatting of the signed-year time axis (mirrors the backend's
/// ADR-0012 model). Pure Dart — no Flutter, no intl — so it is cheap to unit-test.
///
/// Astronomical year numbering: year 0 = 1 BC, year -1 = 2 BC, … so a BC label is
/// `1 - year`.
library;

/// Time precision, matching the API's `time_precision` values.
enum TimePrecision {
  exact,
  day,
  month,
  year,
  decade,
  century,
  era;

  static TimePrecision parse(String s) =>
      values.firstWhere((e) => e.name == s, orElse: () => TimePrecision.day);
}

const List<String> _months = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/// Group an integer's digits with thousands separators (e.g. 4000000 -> "4,000,000").
/// Ordinary 4-digit years are left ungrouped ("2026", not "2,026").
String _grouped(int n) {
  final s = n.abs().toString();
  if (s.length <= 4) return s;
  final buf = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) {
      buf.write(',');
    }
    buf.write(s[i]);
  }
  return buf.toString();
}

String _ordinal(int n) {
  if (n % 100 >= 11 && n % 100 <= 13) return '${n}th';
  switch (n % 10) {
    case 1:
      return '${n}st';
    case 2:
      return '${n}nd';
    case 3:
      return '${n}rd';
    default:
      return '${n}th';
  }
}

/// The astronomical year an instant `t` falls in (floor toward -∞).
int yearOf(double t) => t.floor();

/// Format a year value as "2026" or "44 BC" (thousands-grouped for deep time).
///
/// Our historical data comes from Wikidata, which uses no year 0 (`-0044` = 44 BC), so a
/// negative stored year `Y` is `|Y| BC`. (Astronomical year 0, which Wikidata never emits,
/// falls back to "1 BC".)
String formatYear(double t) {
  final y = yearOf(t);
  if (y > 0) return _grouped(y);
  return '${_grouped(y == 0 ? 1 : -y)} BC';
}

/// Format an exact instant as "11 Mar 2026" (UTC fields).
String formatDate(DateTime dt) {
  final d = dt.toUtc();
  return '${d.day} ${_months[d.month - 1]} ${d.year}';
}

/// A human, precision-aware label for an anchor `t`.
String formatLabel(double t, TimePrecision precision, {DateTime? instant}) {
  final y = yearOf(t);
  switch (precision) {
    case TimePrecision.exact:
    case TimePrecision.day:
      return instant != null ? formatDate(instant) : formatYear(t);
    case TimePrecision.month:
      // The exact month lives in `instant` when present; else fall back to the year.
      if (instant != null) {
        final m = instant.toUtc();
        return '${_months[m.month - 1]} ${m.year}';
      }
      return formatYear(t);
    case TimePrecision.year:
      return formatYear(t);
    case TimePrecision.decade:
      if (y > 0) return '${(y ~/ 10) * 10}s';
      return formatYear(t);
    case TimePrecision.century:
      if (y > 0) return '${_ordinal((y - 1) ~/ 100 + 1)} century';
      final bc = y == 0 ? 1 : -y; // Wikidata no-year-0 convention
      return '${_ordinal((bc - 1) ~/ 100 + 1)} century BC';
    case TimePrecision.era:
      return 'c. ${formatYear(t)}';
  }
}
