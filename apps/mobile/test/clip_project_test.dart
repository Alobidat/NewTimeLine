import 'package:chronos_app/creator/clip_project.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ClipProject upload params (mirrors backend normalize_edit_spec)', () {
    test('a fresh project has no edits', () {
      const p = ClipProject();
      expect(p.hasEdits, isFalse);
      expect(p.uploadTrimStart, isNull);
      expect(p.uploadTrimEnd, isNull);
      expect(p.uploadSpeed, isNull);
    });

    test('a positive trim window is kept and rounded to ms', () {
      const p = ClipProject(trimStart: 1.500777, trimEnd: 9.0, durationS: 12);
      expect(p.uploadTrimStart, 1.501);
      expect(p.uploadTrimEnd, 9.0);
      expect(p.hasEdits, isTrue);
    });

    test('an end-not-after-start window is dropped, speed survives', () {
      const p = ClipProject(trimStart: 5, trimEnd: 5, speed: 2.0);
      expect(p.uploadTrimStart, isNull);
      expect(p.uploadTrimEnd, isNull);
      expect(p.uploadSpeed, 2.0);
    });

    test('zero/negative trims are no-ops', () {
      const p = ClipProject(trimStart: 0, trimEnd: 0);
      expect(p.hasEdits, isFalse);
    });

    test('speed is clamped to the atempo range and 1.0 drops out', () {
      expect(const ClipProject(speed: 10).uploadSpeed, ClipProject.maxSpeed);
      expect(const ClipProject(speed: 0.01).uploadSpeed, ClipProject.minSpeed);
      expect(const ClipProject(speed: 1.0).uploadSpeed, isNull);
    });

    test('canTrim requires a known positive duration', () {
      expect(const ClipProject().canTrim, isFalse);
      expect(const ClipProject(durationS: 0).canTrim, isFalse);
      expect(const ClipProject(durationS: 8).canTrim, isTrue);
    });

    test('copyWith can clear a trim bound', () {
      const p = ClipProject(trimStart: 2, trimEnd: 9, durationS: 10);
      final cleared = p.copyWith(clearTrimStart: true);
      expect(cleared.uploadTrimStart, isNull);
      expect(cleared.uploadTrimEnd, 9.0);
    });
  });
}
