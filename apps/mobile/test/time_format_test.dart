import 'package:chronos_app/domain/time_format.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('formatYear', () {
    test('AD years group thousands', () {
      expect(formatYear(2026.4), '2026');
      expect(formatYear(365.6), '365');
      expect(formatYear(4000000.0), '4,000,000');
    });

    test('BC uses Wikidata no-year-0 convention (-Y = Y BC)', () {
      expect(formatYear(0.5), '1 BC'); // astronomical year 0 fallback
      expect(formatYear(-1.0), '1 BC'); // Wikidata -0001 = 1 BC
      expect(formatYear(-43.99), '44 BC'); // floor → -44 → 44 BC
    });
  });

  group('formatLabel', () {
    test('year precision', () {
      expect(formatLabel(1956.0, TimePrecision.year), '1956');
    });

    test('decade precision', () {
      expect(formatLabel(1956.0, TimePrecision.decade), '1950s');
    });

    test('century precision AD and BC', () {
      expect(formatLabel(1956.0, TimePrecision.century), '20th century');
      expect(formatLabel(-43.0, TimePrecision.century), '1st century BC');
    });

    test('era precision prefixes c.', () {
      expect(formatLabel(-4000000.0, TimePrecision.era), 'c. 4,000,000 BC');
    });

    test('day precision uses the instant when present', () {
      final dt = DateTime.utc(2026, 3, 11);
      expect(
        formatLabel(2026.19, TimePrecision.day, instant: dt),
        '11 Mar 2026',
      );
    });
  });

  test('TimePrecision.parse falls back to day', () {
    expect(TimePrecision.parse('century'), TimePrecision.century);
    expect(TimePrecision.parse('nonsense'), TimePrecision.day);
  });
}
