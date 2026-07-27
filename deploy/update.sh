#!/usr/bin/env bash
# Pull latest code, rebuild, and restart.
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APPDIR"

git pull --ff-only
"$APPDIR/.venv/bin/pip" install -q -r requirements.txt

# Reinstall units so sandbox / path changes take effect.
sed -e "s|__USER__|${SUDO_USER:-$USER}|g" -e "s|__APPDIR__|$APPDIR|g" \
  "$APPDIR/deploy/sofar-bot.service" | sudo tee /etc/systemd/system/sofar-bot.service >/dev/null

if systemctl list-unit-files sofar-web.service >/dev/null 2>&1 &&
  systemctl is-enabled --quiet sofar-web 2>/dev/null; then
  sed -e "s|__USER__|${SUDO_USER:-$USER}|g" -e "s|__APPDIR__|$APPDIR|g" \
    "$APPDIR/deploy/sofar-web.service" | sudo tee /etc/systemd/system/sofar-web.service >/dev/null
  if [ "${SKIP_WEB_BUILD:-0}" = "1" ]; then
    echo "==> Skipping web build (SKIP_WEB_BUILD=1)"
  else
    (cd web && npm ci && npm run build)
  fi
  sudo systemctl daemon-reload
  sudo systemctl restart sofar-web
else
  sudo systemctl daemon-reload
fi

if command -v caddy >/dev/null 2>&1 && [ -f "$APPDIR/deploy/Caddyfile" ]; then
  sed -e "s|__APPDIR__|$APPDIR|g" \
    "$APPDIR/deploy/Caddyfile" | sudo tee /etc/caddy/Caddyfile >/dev/null
  sudo systemctl reload caddy 2>/dev/null || sudo systemctl restart caddy 2>/dev/null || true
fi

sudo systemctl restart sofar-bot
sudo systemctl --no-pager --lines=0 status sofar-bot || true
