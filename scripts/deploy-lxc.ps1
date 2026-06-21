# Deploy the current commit to the on-site LXC (app-host at 192.168.2.45).
#
# Invoked automatically by the git post-commit hook (.githooks/post-commit), or run by hand:
#   powershell -ExecutionPolicy Bypass -File scripts/deploy-lxc.ps1
#
# It pushes the branch, fast-forwards the LXC checkout, and — only when the relevant files
# changed in this commit — rebuilds the API/agents images and/or rebuilds + ships the Flutter
# web bundle into nginx's webdist. Progress is appended to deploy.log at the repo root.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logFile = Join-Path $root "deploy.log"

function Log($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Add-Content -Path $logFile -Value $line
  Write-Output $line
}

$key    = Join-Path $HOME ".ssh\newtimeline_deploy"
$lxc    = "root@192.168.2.45"
$remote = "/opt/newtimeline"
$sshArgs = @("-i", $key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", $lxc)

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
$desc = (git log -1 --format='%h %s')
Log "=== deploy start: $desc (branch $branch) ==="

# What changed in this commit decides which heavy steps run.
git rev-parse --verify -q HEAD~1 *> $null
if ($LASTEXITCODE -eq 0) { $changed = git diff --name-only HEAD~1 HEAD } else { $changed = git ls-files }
$backend = @($changed | Where-Object { $_ -match '^(services|packages|db)/' }).Count -gt 0
$web     = @($changed | Where-Object { $_ -match '^apps/mobile/' }).Count -gt 0
Log "changed -> backend=$backend web=$web"

try {
  Log "push $branch"
  (git push origin $branch 2>&1) | ForEach-Object { Log "  $_" }
} catch { Log "push ERROR: $_" }

try {
  Log "LXC: fetch + reset to origin/$branch"
  (ssh @sshArgs "cd $remote && git fetch origin -q && git reset --hard origin/$branch" 2>&1) |
    ForEach-Object { Log "  $_" }
} catch { Log "pull ERROR: $_" }

if ($backend) {
  try {
    Log "LXC: rebuild api+agents, restart api"
    (ssh @sshArgs "cd $remote && docker compose build api agents && docker compose up -d api" 2>&1) |
      Select-Object -Last 6 | ForEach-Object { Log "  $_" }
  } catch { Log "backend ERROR: $_" }
}

if ($web) {
  try {
    Log "build Flutter web"
    Push-Location (Join-Path $root "apps\mobile")
    (flutter build web --no-tree-shake-icons --no-wasm-dry-run 2>&1) |
      Select-Object -Last 2 | ForEach-Object { Log "  $_" }
    Pop-Location
    $tgz = Join-Path $env:TEMP "webdist-deploy.tgz"
    tar -czf $tgz -C (Join-Path $root "apps\mobile\build\web") .
    Log "ship webdist bundle"
    (scp -i $key -o BatchMode=yes -o StrictHostKeyChecking=accept-new $tgz "${lxc}:$remote/webdist-deploy.tgz" 2>&1) |
      ForEach-Object { Log "  $_" }
    (ssh @sshArgs "cd $remote && find webdist -mindepth 1 -delete && tar --no-same-owner -xzf webdist-deploy.tgz -C webdist && rm -f webdist-deploy.tgz && find webdist -type d -exec chmod 755 {} + && find webdist -type f -exec chmod 644 {} +" 2>&1) |
      ForEach-Object { Log "  $_" }
    Remove-Item $tgz -ErrorAction SilentlyContinue
    Log "webdist updated (browsers must hard-refresh to drop the old service worker)"
  } catch { Log "web ERROR: $_" }
}

$health = (ssh @sshArgs "curl -s -o /dev/null -w '%{http_code}' 'http://localhost:8000/timeline/summary?t0=1900&t1=2030'" 2>&1)
Log "api /timeline/summary -> HTTP $health"
Log "=== deploy done ==="
