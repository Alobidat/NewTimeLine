#!/usr/bin/env bash
# Provision the on-site LXC (192.168.2.45, Ubuntu 24.04) as the Chronos development box:
# a `dev` user, the toolchain (Node, Flutter, Python venv), a dev clone, and Claude Code.
# Run as root on the LXC. Idempotent-ish; safe to re-run. Records what was set up manually so
# the box can be rebuilt. See docs note [[deploy-lxc-automation]].
#
# Prereqs: the LXC disk grown to ~50 GB (native Flutter won't fit in the original 15 GB).
set -euo pipefail

DEV_USER=dev
DEV_HOME=/home/$DEV_USER
DEV_CLONE=$DEV_HOME/newtimeline-dev
REPO_URL=https://github.com/Alobidat/NewTimeLine.git
BRANCH=feat/phase-3b-history-graph

# 1. dev user (sudo + docker, key-only login)
id "$DEV_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$DEV_USER"
usermod -aG sudo "$DEV_USER"
getent group docker >/dev/null && usermod -aG docker "$DEV_USER"
echo "$DEV_USER ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/90-dev && chmod 440 /etc/sudoers.d/90-dev
install -d -m 700 -o "$DEV_USER" -g "$DEV_USER" "$DEV_HOME/.ssh"
# (authorized_keys seeded separately with the operator's public key)

# 2. base toolchain + Node LTS
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq build-essential curl git unzip xz-utils ca-certificates pkg-config python3-venv python3-pip
curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
apt-get install -y -qq nodejs

# 3. Claude Code CLI
npm install -g @anthropic-ai/claude-code

# 4. Flutter SDK (web), owned by the dev user
[ -d /opt/flutter ] || git clone --depth 1 -b stable https://github.com/flutter/flutter.git /opt/flutter
chown -R "$DEV_USER:$DEV_USER" /opt/flutter
echo 'export PATH="$PATH:/opt/flutter/bin"' >/etc/profile.d/flutter.sh
sudo -u "$DEV_USER" -H bash -lc 'export PATH=$PATH:/opt/flutter/bin; flutter config --enable-web --no-analytics; flutter precache --web'

# 5. dev clone + Python venv + git push key
sudo -u "$DEV_USER" -H bash -l <<EOF
set -e
[ -d "$DEV_CLONE" ] || git clone -q "$REPO_URL" "$DEV_CLONE"
cd "$DEV_CLONE"
git checkout -q "$BRANCH"
git config core.hooksPath .githooks
git config user.name  "Chronos Dev (LXC)"
git config user.email "dev@newtimeline-lxc"
python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -e ./packages/core -e ./services/api -e ./services/agents pytest ruff
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N "" -C "dev@newtimeline-lxc" -f ~/.ssh/id_ed25519 -q
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null
echo "Add this as a WRITE deploy key on the GitHub repo for push:"; cat ~/.ssh/id_ed25519.pub
EOF

# 6. let root operate the dev clone + live checkout during deploys
git config --global --add safe.directory "$DEV_CLONE"
git config --global --add safe.directory /opt/newtimeline

echo "Done. Set ANTHROPIC_API_KEY for $DEV_USER and add the printed deploy key to GitHub."
