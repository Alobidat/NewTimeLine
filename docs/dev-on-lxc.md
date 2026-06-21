# Developing on the LXC (192.168.2.45)

This box (`NewTimeLine`, Ubuntu 24.04) is the Chronos dev + deploy host.

## Connect (VS Code Remote-SSH)
On your machine, add to `~/.ssh/config`:
```
Host newtimeline
    HostName 192.168.2.45
    User dev
    IdentityFile ~/.ssh/id_ed25519
```
Then VS Code → "Remote-SSH: Connect to Host" → `newtimeline` → open
`/home/dev/newtimeline-dev`. Accept the recommended extensions (Dart/Flutter,
Python, Docker, Claude Code).

## Layout
- `~/newtimeline-dev` — the dev clone (edit here). Python venv at `.venv`.
- `/opt/newtimeline` — the live docker stack + nginx `webdist` (deploy target; do
  not edit in place — the deploy `reset --hard`es it).
- Flutter SDK at `/opt/flutter`; `flutter build web` works (web only).

## Deploy loop
Every commit fires `.githooks/post-commit` → `scripts/deploy-lxc.sh`: syncs
`/opt/newtimeline` to the commit and rebuilds only what changed (web → copied into
`webdist`; backend → `docker compose build api agents`). Progress in `deploy.log`.
The app is served at `:8080`; hard-refresh (Ctrl+Shift+R) after a web deploy.

## Tooling
- Tests: `./.venv/bin/pytest packages/core/tests`
- Claude Code: `claude` (needs `ANTHROPIC_API_KEY` or `claude login`).
