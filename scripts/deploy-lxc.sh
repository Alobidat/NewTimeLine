#!/usr/bin/env bash
# LXC-native deploy — runs on the dev box after each commit (see .githooks/post-commit).
# Syncs the live stack at /opt/newtimeline to THIS dev clone's current commit and rebuilds only
# what changed. All-local (same host): the web bundle is copied straight into nginx's webdist,
# no scp. Progress is appended to deploy.log at the repo root.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LIVE=/opt/newtimeline
LOG="$ROOT/deploy.log"
FLUTTER=/opt/flutter/bin/flutter
log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG"; }

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
log "=== deploy start: $(git log -1 --format='%h %s') (branch $BRANCH) ==="

if git rev-parse --verify -q HEAD~1 >/dev/null; then
  CHANGED="$(git diff --name-only HEAD~1 HEAD)"
else
  CHANGED="$(git ls-files)"
fi
BACKEND=false; WEB=false; ADMIN=false
echo "$CHANGED" | grep -qE '^(services|packages|db)/' && BACKEND=true
echo "$CHANGED" | grep -qE '^apps/mobile/' && WEB=true
echo "$CHANGED" | grep -qE '^apps/admin/' && ADMIN=true
log "changed -> backend=$BACKEND web=$WEB admin=$ADMIN"

# 1. Best-effort push to GitHub (source of truth); never blocks the deploy.
if git push origin "$BRANCH" >>"$LOG" 2>&1; then log "pushed $BRANCH"; else log "push skipped/failed (deploy key may be unset)"; fi

# 2. Sync the live checkout to THIS commit via a local fetch (no GitHub round-trip needed).
sudo git -C "$LIVE" fetch -q "$ROOT" "$BRANCH" && sudo git -C "$LIVE" reset --hard -q FETCH_HEAD
log "live checkout -> $(sudo git -C "$LIVE" rev-parse --short HEAD)"

# 3. Web bundle: build here, copy into nginx's webdist.
if $WEB; then
  log "build Flutter web"
  if ( cd apps/mobile && "$FLUTTER" build web --pwa-strategy=none --no-tree-shake-icons --no-wasm-dry-run ) >>"$LOG" 2>&1; then
    sudo rm -rf "$LIVE"/webdist/*
    sudo cp -a apps/mobile/build/web/. "$LIVE"/webdist/
    # Overwrite Flutter's SW with the kill-switch so any client still running the old caching
    # SW clears itself (new visitors don't register one — --pwa-strategy=none above).
    sudo cp -f infra/webapp/flutter_service_worker.js "$LIVE"/webdist/flutter_service_worker.js
    sudo find "$LIVE"/webdist -type d -exec chmod 755 {} +
    sudo find "$LIVE"/webdist -type f -exec chmod 644 {} +
    log "webdist updated (hard-refresh to drop the old service worker)"
  else
    log "web build/ship FAILED"
  fi
fi

# 3b. Admin Portal bundle: build same-origin (API under /api) into webdist-admin; ensure the
# adminapp container is up. The Admin API is open in dev — bake an ADMIN_TOKEN to lock it.
if $ADMIN; then
  log "build Admin Portal web"
  if ( cd apps/admin && "$FLUTTER" build web --dart-define=API_BASE_URL=/api \
        --pwa-strategy=none --no-tree-shake-icons --no-wasm-dry-run ) >>"$LOG" 2>&1; then
    sudo mkdir -p "$LIVE"/webdist-admin
    sudo rm -rf "$LIVE"/webdist-admin/*
    sudo cp -a apps/admin/build/web/. "$LIVE"/webdist-admin/
    sudo cp -f infra/webapp/flutter_service_worker.js "$LIVE"/webdist-admin/flutter_service_worker.js
    sudo find "$LIVE"/webdist-admin -type d -exec chmod 755 {} +
    sudo find "$LIVE"/webdist-admin -type f -exec chmod 644 {} +
    ( cd "$LIVE" && docker compose up -d adminapp ) >>"$LOG" 2>&1
    log "webdist-admin updated + adminapp up (hard-refresh to drop the old service worker)"
  else
    log "admin build/ship FAILED"
  fi
fi

# 4. Backend images. Rebuild migrate too — it carries the Alembic scripts, so a new
# migration must land in its image or `up -d api` (which runs migrate) fails to reach head.
if $BACKEND; then
  log "rebuild migrate+api+agents+worker, restart api+worker"
  # The worker is a long-running service (queue consumer + AI-user scheduler tick); it shares
  # the agents image, so building agents covers it. Start/refresh it alongside the api.
  if ( cd "$LIVE" && docker compose build migrate api agents \
        && docker compose up -d api worker ) >>"$LOG" 2>&1; then
    log "backend redeployed (api + worker up)"
    # Recreating the api gives it a new container IP, but the nginx frontends cache the old one
    # at startup (proxy_pass http://api:8000) → 502 on /api/* until they re-resolve. Restart them.
    if ( cd "$LIVE" && docker compose restart webapp adminapp ) >>"$LOG" 2>&1; then
      log "frontends restarted (re-resolve api)"
    else
      log "frontend restart FAILED"
    fi
  else
    log "backend redeploy FAILED"
  fi
fi

HEALTH="$(curl -s -o /dev/null -w '%{http_code}' 'http://localhost:8000/timeline/summary?t0=1900&t1=2030')"
log "api /timeline/summary -> HTTP $HEALTH"
log "=== deploy done ==="
