# Administration Portal

A first-class, role-gated control plane for the whole platform — **everything the agents
do, spend, and touch is configured and monitored here**, alongside content moderation,
user administration, and system configuration. Nothing about agent behavior is hard-coded;
it is read from a **Config Service** the portal writes to.

## 1. Principles
- **Config over code:** agent behavior, budgets, feeds, thresholds, model choices, and
  severity weights live in a versioned, DB-backed config — changeable without redeploy.
- **Hot reload:** services subscribe to config changes (via the cache/pubsub) and apply
  them without restart; every change is versioned and reversible.
- **Audited:** every admin action is recorded (who, what, before→after, when).
- **RBAC:** distinct roles — `super_admin`, `ops` (agents/infra), `moderator` (content),
  `analyst` (read-only dashboards).

## 2. The Config Service (foundation)
A central settings store every component reads from.
```sql
CREATE TABLE config (
  key         text PRIMARY KEY,          -- e.g. 'agents.enricher.model'
  value       jsonb NOT NULL,
  scope       text NOT NULL,             -- global | agent:<name> | feed:<id> | severity | feature_flag
  version     integer NOT NULL DEFAULT 1,
  updated_by  uuid,                       -- admin user
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE config_audit (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key        text NOT NULL,
  old_value  jsonb,
  new_value  jsonb,
  changed_by uuid NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT now()
);
```
On write, the portal bumps `version`, appends to `config_audit`, and publishes a
`config.changed` event so live workers pick up the new value.

## 3. What the portal controls

### 3.1 Agent management (the core ask)
For **each agent** (ingestor, normalizer, deduper, enricher, geocoder, relation-linker,
severity-scorer, tier-3 dig) and globally:
- **Enable / disable / pause** the agent.
- **Schedule** (poll/run intervals, concurrency, batch sizes).
- **Capabilities — "what they can do":** scoped permissions, e.g. which feeds an ingestor
  may read, whether the enricher may call the LLM, whether tier-3 may create *new* events,
  max recursion/dig depth, allowed entity sources (Wikidata only? geocoding API allowed?).
- **Model selection per tier** (which Claude tier for dedup/enrich vs tier-3).
- **Quality knobs:** dedup similarity thresholds, the LLM-adjudication band, geocoding
  confidence floor, neutrality/grounding prompt parameters.

### 3.2 Budgets & cost guardrails
- **Token/$ budgets:** per-agent and global, with **daily/monthly caps**.
- **Degrade behavior on cap:** what happens when budget is hit (e.g. feed-only mode,
  queue-and-wait, alert-only). Configurable per agent.
- **Live spend meters** vs budget; projected burn; alerts at thresholds (e.g. 80%).
- **Rate limits** per external API (news APIs, geocoder) to respect provider quotas/cost.

### 3.3 Feed / source management
- Add / remove / configure **feeds** (URL, type, schedule, parser, region/language).
- Store provider **API keys/secrets** (secret-managed, never plaintext in config rows).
- Per-feed health: last fetch, items ingested, error rate, dedup contribution.
- **Source domain reputation** overrides (set/adjust `sources.quality_score` defaults).

### 3.4 Severity & ranking tuning
- Edit the **severity weights** (`w_impact`, `w_social`, `w_corroboration`) and
  normalization curves live; preview impact on a sample before committing.
- Confidence thresholds for the "verified/unverified" badges.

### 3.5 Content moderation
- **Comment queue:** review flagged/auto-flagged comments; remove/restore; warn/suspend.
- **Event ops:** retract, merge, split, edit metadata, force re-enrich, hide.
- **Source disputes:** review community-disputed sources; override quality; remove.
- **User reports** triage.

### 3.6 User & community administration
- Search users; view profiles, contributions, reputation.
- Roles & permissions; **reputation overrides**; ban/suspend/shadow-limit for abuse.
- Bulk actions for spam waves; appeal handling.

### 3.7 System configuration
- **Feature flags** (toggle features per platform/region/cohort).
- Notification policy defaults; recommendation on/off; i18n/region settings.
- Maintenance mode.

## 4. Monitoring & observability (dashboards)
- **Pipeline health:** per-stage throughput, queue depth, ingestion lag, error rates,
  retry/dead-letter counts; one-click **replay** from `ingest_items`.
- **Cost:** LLM token spend by agent/tier/day vs budget; geocoding/API spend.
- **Quality:** dedup merge/split rate, enrichment validation failures, geocode hit rate,
  events published/hr, average confidence.
- **Engagement:** DAU/MAU, reactions, comments, validations, subscriptions, notif delivery.
- **System:** service health, latency, DB/queue/cache metrics (via the standard
  observability stack — OpenTelemetry/Prometheus/dashboards).

## 4b. Architecture — self-extending (manifest + schema driven) · ADR-0019
The portal must stay cheap to extend as we add agents/services/stores, so it does **not**
hard-code a screen per component. Everything renders from three generic contracts:

1. **Component registry** (`chronos_core.registry`) — each component is a
   `ComponentManifest`: `id` (`agent:enrich`), `kind` (agent|service|store), title,
   `capabilities`, `config_prefix`, `enabled_key`, declared `actions`
   (enable/disable/pause/run-now), and notable `stat_keys`. **Adding a component = appending
   one manifest** (plus its config specs). It then auto-appears in the portal with a health
   card, an auto-generated config form, and its action buttons — no Admin API or UI changes.
2. **Schema-driven config** (`chronos_core.config_spec`) — every config key has a typed
   `ConfigSpec` (type, default, scope, label/help, min/max/enum/secret, owning component).
   This is the **single source of truth**: `config_service.DEFAULTS` is derived from it, the
   Admin API validates writes against it, and the UI generates forms from it.
3. **Observable runtime** — `agent_runs` records each execution (running→ok/error + the
   agent's result counts), written via `chronos_core.runs.record_run`. Health (liveness, lag,
   success rate, "what's running now") is **derived** by the pure `chronos_core.domain.health`.

**Admin API** (implemented): `/admin/overview`, `/admin/components` (+ `/{id}`,
`/{id}/actions/{action}`), `/admin/config` (GET + `PUT /{key}` validated), `/admin/runs`,
`/admin/storage`, `/admin/system`, `/admin/users` (501 until Phase 4). All gated by
`require_admin` (bearer `admin_token`; open in dev when unset) and config writes are audited.

## 5. Implementation
- **Frontend:** a dedicated **Flutter** `apps/admin` app — **one codebase → web *and* mobile
  apps** (ADR-0002), reusing a shared design system + API client. Screens are **data-driven**
  (generated from the manifest/spec contract above), so the same build serves a full web
  console and a capable mobile admin. **Polling-first** for live tiles; SSE/WebSocket push is
  added once the real-time gateway exists. *(Shell built: Overview, Components+detail, Config,
  Runs, Storage, System screens, schema-driven config editor, responsive rail/bottom-nav.)*
- **Backend (done):** the namespaced **Admin API** (`/admin/*`) behind `require_admin`,
  writing to the Config Service (audited + version-bumped) and reading the registry / specs /
  `agent_runs`. RBAC roles + OIDC arrive in Phase 4; today it's a bearer-token gate.
- **Secrets:** API keys/credentials go to a secret manager; config rows hold references,
  not raw secrets (`ConfigSpec.secret` masks them in API reads).

## 6. Where it sits in the roadmap
The Config Service ships early (so agents are configurable from the start). The portal UI
is built incrementally: a minimal agent/budget/feed console in **Phase 3** (when agents go
live), expanding to moderation in **Phase 4**, recommendations/flags in **Phase 5**, and
full dashboards by **Phase 7**. See [roadmap.md](roadmap.md).
