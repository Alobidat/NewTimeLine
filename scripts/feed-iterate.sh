#!/usr/bin/env bash
# Build the mobile web app, ship it to the live webdist, and screenshot the feed via headless
# chrome. Used to iterate on the web video/overlay rendering with real visual feedback.
set -uo pipefail
cd /home/dev/newtimeline-dev/apps/mobile
echo "[$(date +%T)] building..."
/opt/flutter/bin/flutter build web --pwa-strategy=none --no-tree-shake-icons --no-wasm-dry-run 2>&1 | tail -1
sudo cp -a build/web/. /opt/newtimeline/webdist/
sudo cp -f /home/dev/newtimeline-dev/infra/webapp/flutter_service_worker.js /opt/newtimeline/webdist/flutter_service_worker.js 2>/dev/null
echo "[$(date +%T)] shipped. measuring..."
cd /tmp/inspect && node run.js 2>&1 | grep -A30 "INSPECT:"
echo "[$(date +%T)] done."
