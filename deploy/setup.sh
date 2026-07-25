#!/usr/bin/env bash
# Install Sofar as a systemd service (no Docker).
# Run from the repo root on the VPS:  bash deploy/setup.sh
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-$USER}"
SERVICE_NAME="sofar-bot"

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

echo "==> Installing systemd unit"
sed -e "s|__USER__|$RUN_USER|g" -e "s|__APPDIR__|$APPDIR|g" \
  "$APPDIR/deploy/$SERVICE_NAME.service" | sudo tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

echo "==> Done. Status:"
sudo systemctl --no-pager status "$SERVICE_NAME" || true
echo
echo "Logs:    journalctl -u $SERVICE_NAME -f"
echo "Restart: sudo systemctl restart $SERVICE_NAME"
