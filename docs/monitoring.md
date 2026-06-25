# System Health & Monitoring

The monitoring subsystem extends the manifest/registry control plane (ADR-0019) with **live
health probes**, **resource metrics**, and (Phase B) **log access + runtime log-level
control** — all rendered in the Admin Portal's *System Health* dashboard. Self-contained: no
Prometheus/Grafana, just Postgres + the Docker Engine API + the stdlib.

## How it works

- **Component health has two sources** (`registry.ComponentManifest.health_source`):
  - `runs` — agents derive health from `agent_runs` (existing behaviour).
  - `probe` — infra/services (Postgres, Redis, RabbitMQ, object store, API, worker, edge
    nginx) get a **live probe** each cycle, written to the `component_health` table.
- **The collector** (`chronos_core.monitoring.collector.Collector`) runs as a worker ticker
  (`monitoring.enabled`, every `monitoring.collector.interval_seconds`) and also on demand via
  the `monitor` agent command. Each cycle it:
  1. probes every `health_source="probe"` component → upserts `component_health`;
  2. pulls per-container CPU/mem/network from the **Docker Engine API** (read-only
     `/var/run/docker.sock`, mapped by the `com.docker.compose.service` label) and host
     disk/mem/CPU from the stdlib → appends `metric_sample` rows;
  3. refreshes the worker heartbeat (`chronos:monitor:heartbeat`) and prunes retention.
- **Severity level** (`ok | warning | degraded | critical`) is orthogonal to status; plane and
  system rollups take the worst level. Thresholds (`monitoring.thresholds`) drive level in
  Phase C; until then level mirrors status.

## Admin API

- `GET /admin/health` — full tree: components grouped by plane (edge/api/processing/store) +
  host gauges + rollup levels.
- `GET /admin/metrics/host` — latest host disk/memory/CPU/load.
- `GET /admin/components/{id}/metrics?metric=&window=` — resource time-series (one series per
  metric) for charts/sparklines.

## Deployment note

The `worker` service mounts `/var/run/docker.sock:ro` (container stats) and `/:/host:ro`
(host disk/mem). Without the socket the collector still probes + samples host/DB metrics; only
per-container resource stats are skipped (logged once).

## Config

`monitoring.*` keys (collector interval, metric/log retention, log-buffer cap, thresholds)
and `logging.*` levels are tunable from the Admin Portal config forms.
