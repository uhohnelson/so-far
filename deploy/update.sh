#!/usr/bin/env bash
# Pull latest code and restart the bot.
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APPDIR"

git pull --ff-only
"$APPDIR/.venv/bin/pip" install -q -r requirements.txt
sudo systemctl restart sofar-bot
sudo systemctl --no-pager status sofar-bot || true
