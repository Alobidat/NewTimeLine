# chronos_app — Flutter client (Phase 2a)

The "magical timeline" client. Phase 2a delivers the signature surface: a scrubbable,
zoomable timeline of world events (live + deep history) with severity visuals, a density
heatline when zoomed out, and an event detail sheet incl. the **sub-timeline**. The map
layer (MapLibre/flutter_map) is Phase 2b.

## Run
The app defaults to the on-site API (`http://192.168.2.45:8000`). Override with
`--dart-define`:
```sh
flutter pub get
flutter run -d chrome   --dart-define=API_BASE_URL=http://192.168.2.45:8000   # web
flutter run -d windows  --dart-define=API_BASE_URL=http://192.168.2.45:8000   # desktop
```
Targets enabled: **web, windows** (add android/ios later with `flutter create --platforms`).

## Interactions
- **Drag** to scrub through time · **pinch / mouse-wheel** to zoom (log-feel, ms → millennia)
- **Tap** an event → detail sheet (summary, sources, sub-timeline)
- **Preset chips** jump to Deep time / Antiquity / Last century / Live
- Zoom out far enough → the server returns **buckets**, drawn as a density heatline

## Layout (small, single-responsibility files; see ../../docs/engineering-standards.md)
```
lib/
  config.dart              API base URL (--dart-define overridable)
  api/models.dart          DTOs mirroring chronos_core.schemas
  api/client.dart          HTTP client (timeline / map / event)
  domain/time_format.dart  signed-year -> label (BC/AD, decade, century, era) — pure, tested
  domain/time_axis.dart    year<->pixel, pan/zoom math — pure, tested
  theme/severity.dart      severity -> colour
  timeline/                controller · layout+hit-test · CustomPainter · screen
  event/                   detail sheet (+ sub-timeline)
test/                      time_format, time_axis, painter smoke (14 tests)
```

## Verify
```sh
dart format lib test
flutter analyze         # clean
flutter test            # 14 pass
flutter build web       # compiles
```

## Notes
- Anonymous (no account) — matches ADR-0007; social/auth is Phase 4.
- `domain/*` is pure Dart (no Flutter) so the tricky time math is unit-tested without a device.
- Web calls the API over plain HTTP; the dev API allows CORS `*` (ENVIRONMENT=dev). For a
  public TLS deployment we'll tighten CORS + serve over https.
