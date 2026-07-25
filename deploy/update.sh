#!/usr/bin/env bash
# Pull latest code, rebuild, and restart.
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APPDIR"

git pull --ff-only
"$APPDIR/.venv/bin/pip" install -q -r requirements.txt

if systemctl list-unit-files sofar-web.service >/dev/null 2>&1 &&
  systemctl is-enabled --quiet sofar-web 2>/dev/null; then
  (cd web && npm ci && npm run build)
  sudo systemctl restart sofar-web
fi

sudo systemctl restart sofar-bot
sudo systemctl --no-pager --lines=0 status sofar-bot || true
