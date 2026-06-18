# apps/ — Flutter clients

Flutter (Dart) front-ends. One codebase per target family; shared logic lives in
[`../packages/`](../packages/).

| Dir | What | Status | Targets |
|-----|------|--------|---------|
| `mobile/` | The main Chronos app — **timeline + event detail + sub-timeline ✅ (Phase 2a)**; map + social later | **Phase 2a done** | Web, Windows (add Android/iOS later) |
| `admin/` | Admin portal — agent/budget/feed config, moderation, dashboards | Planned (Phase 3+) | Flutter Web |

Conventions: feature-first libraries, thin public APIs via barrel files, `dart format` +
`flutter analyze`. See [../docs/engineering-standards.md](../docs/engineering-standards.md)
and [../docs/timeline-ux.md](../docs/timeline-ux.md).
