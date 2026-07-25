#!/usr/bin/env bash
# Install Sofar as systemd services (no Docker).
# Run from the repo root on the VPS:  bash deploy/setup.sh
#
#   bash deploy/setup.sh            bot + web app
#   bash deploy/setup.sh --bot-only just the Telegram bot
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-$USER}"
WITH_WEB=1
[ "${1:-}" = "--bot-only" ] && WITH_WEB=0

install_unit() {
  local name="$1"
  sed -e "s|__USER__|$RUN_USER|g" -e "s|__APPDIR__|$APPDIR|g" \
    "$APPDIR/deploy/$name.service" | sudo tee "/etc/systemd/system/$name.service" >/dev/null
}

echo "==> Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pip sqlite3

if ! swapon --show | grep -q .; then
  echo "==> No swap found; creating 1G swapfile"
  sudo fallocate -l 1G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Creating virtualenv"
python3 -m venv "$APPDIR/.venv"
"$APPDIR/.venv/bin/pip" install --upgrade pip
"$APPDIR/.venv/bin/pip" install -r "$APPDIR/requirements.txt"

mkdir -p "$APPDIR/data"

if [ ! -f "$APPDIR/.env" ]; then
  echo "!! $APPDIR/.env is missing. Copy .env.example and add your keys, then re-run."
  exit 1
fi
chmod 600 "$APPDIR/.env"

if [ "$WITH_WEB" = "1" ]; then
  if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -c2- | cut -d. -f1)" -lt 20 ]; then
    echo "==> Installing Node 22 (needed to build the web app)"
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
  fi
  echo "==> Building web app"
  (cd "$APPDIR/web" && npm ci && npm run build)
fi

echo "==> Installing systemd units"
install_unit sofar-bot
[ "$WITH_WEB" = "1" ] && install_unit sofar-web

sudo systemctl daemon-reload
sudo systemctl enable --now sofar-bot
[ "$WITH_WEB" = "1" ] && sudo systemctl enable --now sofar-web

echo "==> Done."
sudo systemctl --no-pager --lines=0 status sofar-bot || true
[ "$WITH_WEB" = "1" ] && { sudo systemctl --no-pager --lines=0 status sofar-web || true; }
echo
echo "Bot logs: journalctl -u sofar-bot -f"
[ "$WITH_WEB" = "1" ] && echo "Web logs: journalctl -u sofar-web -f"
[ "$WITH_WEB" = "1" ] && echo "Web app is on 127.0.0.1:8000 - put Caddy or nginx in front for HTTPS."
