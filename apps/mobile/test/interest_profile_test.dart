// Tests InterestProfile.fromJson resolving the live `/me/interests` shape: entity/place/source
// uuids are mapped to human names via the `labels` map (the profile chips showed raw uuids
// before), while categories stay as-is.

import 'package:chronos_app/api/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('resolves entity/place/source uuids to names via labels; categories stay literal', () {
    final profile = InterestProfile.fromJson({
      'entities': {'1349982a-uuid': 2.0, '1decabaa-uuid': 1.5},
      'places': {'1349982a-uuid': 1.0},
      'categories': {'science': 3.0},
      'sources': {'af27-uuid': 0.5},
      'labels': {
        '1349982a-uuid': 'United States',
        '1decabaa-uuid': 'SpaceX',
        'af27-uuid': 'Antares Launch Replays',
      },
      'sample_size': 12,
    });

    final byLabel = {for (final it in profile.items) it.label: it};
    expect(byLabel.keys, containsAll(<String>[
      'United States', 'SpaceX', 'science', 'Antares Launch Replays',
    ]));
    // No raw uuid leaks into a chip label.
    expect(profile.items.any((it) => it.label.contains('uuid')), isFalse);
    // The category keeps its literal name and carries no id.
    expect(byLabel['science']!.kind, 'categories');
    expect(byLabel['science']!.id, isNull);
    // A resolved entity keeps its id (for follow/match) but shows the name.
    expect(byLabel['SpaceX']!.id, '1decabaa-uuid');
    expect(profile.sampleSize, 12);
  });

  test('falls back to the raw key when a label is missing', () {
    final profile = InterestProfile.fromJson({
      'entities': {'unknown-uuid': 1.0},
      'labels': {},
      'sample_size': 1,
    });
    expect(profile.items.single.label, 'unknown-uuid');
  });
}
