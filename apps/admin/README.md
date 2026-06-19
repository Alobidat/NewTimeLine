# Chronos Admin Portal (`apps/admin`)

A Flutter app — **one codebase → web + mobile/desktop** (ADR-0002) — that operates the
platform: agent health & control, runtime configuration, run history, storage, and system
status. It renders entirely from the **Admin API** (`/admin/*`) which is itself driven by
the component registry + config specs (ADR-0019), so new backend components appear here
automatically.

## Run

```bash
flutter pub get
flutter analyze
flutter test

# Point at an API + admin token (the API runs open in dev when no token is set):
flutter run -d chrome \
  --dart-define=API_BASE_URL=http://192.168.2.45:8000 \
  --dart-define=ADMIN_TOKEN=your-token
```

Platform scaffolding (`web/`, `android/`, …) is generated on demand: `flutter create .`
from this directory adds the targets without touching `lib/`.

## Layout
- `lib/api/` — `AdminClient` + DTOs mirroring `chronos_core.schemas.admin`.
- `lib/widgets/` — `PollingBuilder` (poll + loading/error/refresh), `ConfigTile`
  (schema-driven field editor), status visuals.
- `lib/screens/` — Overview, Components (+ detail), Config, Runs, Storage, System.
- `lib/shell/` — responsive NavigationRail (wide) / NavigationBar (phone).

Live updates are **polling-based** (`AdminConfig.pollInterval`); a realtime gateway
(SSE/WebSocket) replaces polling in a later phase.
