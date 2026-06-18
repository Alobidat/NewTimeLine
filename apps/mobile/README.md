# chronos_app — Flutter client (Phase 2)

The "magical timeline" client: a **linked map + timeline** of world events (live + deep
history). Scrub/zoom the timeline, pan the map — they share one time window. Severity
visuals, a density heatline when zoomed out, and an event detail sheet incl. the
**sub-timeline**. Map uses `flutter_map` with OSM tiles (ADR-0013).

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
- **Timeline:** drag to scrub · pinch / mouse-wheel to zoom (log-feel, ms → millennia)
- **Map:** pan/zoom to refilter events by viewport; markers sized/coloured by severity
- Timeline + map share one time window — moving either updates the other
- **Tap** an event (on map or timeline) → detail sheet (summary, sources, sub-timeline)
- **Preset chips** jump to Deep time / Antiquity / Last century / Live
- Zoom the timeline out far enough → the server returns **buckets**, drawn as a heatline

## Layout (small, single-responsibility files; see ../../docs/engineering-standards.md)
```
lib/
  config.dart              API base URL (--dart-define overridable)
  state/time_window.dart   shared time range (links map + timeline)
  api/models.dart          DTOs mirroring chronos_core.schemas
  api/client.dart          HTTP client (timeline / map / event)
  domain/time_format.dart  signed-year -> label (BC/AD, decade, century, era) — pure, tested
  domain/time_axis.dart    year<->pixel, pan/zoom math — pure, tested
  theme/severity.dart      severity -> colour
  timeline/                controller · layout+hit-test · CustomPainter · panel
  map/                     model · view (flutter_map) · bbox helper (pure, tested)
  event/                   detail sheet (+ sub-timeline)
  shell/app_shell.dart     links map (top) + timeline (bottom) via shared window
test/                      time_format, time_axis, geo, painter smoke (16 tests)
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
