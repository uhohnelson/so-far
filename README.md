# Sofar

Personal movie and TV tracker. Telegram bot first; web later. Same backend for both.

## Setup

1. Python 3.11+ recommended.
2. Create a Telegram bot with [BotFather](https://t.me/BotFather) and get a TMDB API key.
3. Copy env and fill secrets:

```bash
cp .env.example .env
```

4. Install and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m bot.main
```

Optional API (for later web / debugging):

```bash
uvicorn server.api:app --reload --port 8000
```

## Bot commands

| Command | What it does |
|---------|----------------|
| `/start` | Home: Search · Continue · My list |
| `/search` | Live search (or `/search the bear` fallback) |
| `/list [want\|watching\|watched]` | Your library |
| `/next` / `/watched` | Continue watching |
| `/cancel` | Cancel season/episode prompt |
| `/help` | Quick tips |

Status words are always **Want · Watching · Watched**. Episode action is **Mark ep**.

### Live search (inline mode)

1. In [@BotFather](https://t.me/BotFather), send `/setinline` for your bot.
2. Placeholder example: `movie or show…`
3. Tap **Search** in Sofar and type.

Filters while typing: `movie dune`, `tv the bear` (or `m:` / `t:`).

## Deploy on a VPS (systemd, no Docker)

The bot uses long polling, so **no inbound ports** are required. The VM only needs outbound HTTPS to Telegram and TMDB, and it idles at roughly 60-90 MB of RAM.

### 1. Clone and configure

```bash
sudo apt update && sudo apt install -y git python3-venv
git clone https://github.com/uhohnelson/so-far.git sofar
cd sofar
cp .env.example .env
nano .env   # set TELEGRAM_BOT_TOKEN and TMDB_API_KEY
```

### 2. Install the service

```bash
bash deploy/setup.sh
```

This creates a venv, installs dependencies, adds a 1 GB swapfile if none exists, and installs + starts the `sofar-bot` systemd unit (which restarts the bot on crash and on reboot).

### 3. Useful commands

```bash
journalctl -u sofar-bot -f          # live logs
sudo systemctl restart sofar-bot
sudo systemctl stop sofar-bot
bash deploy/update.sh               # git pull + reinstall deps + restart
```

The SQLite file lives at `data/sofar.db` inside the checkout, so back it up with `cp` or `scp`.

### 4. Optional: seed your existing library

From your Mac, after the service has run once:

```bash
ssh you@YOUR_VPS_IP 'sudo systemctl stop sofar-bot'
scp data/sofar.db you@YOUR_VPS_IP:~/sofar/data/sofar.db
ssh you@YOUR_VPS_IP 'sudo systemctl start sofar-bot'
```

Or start empty on the VPS and re-add titles - fine for MVP.

### Notes

- Works on Oracle Always Free Ampere (ARM); everything here is pure Python, no arch-specific images.
- Open **egress** is enough; you do not need to open 80/443 for the bot.
- Keep only **one** bot process running (stop your Mac bot before going live on the VPS, or Telegram will conflict).
- `Dockerfile` / `docker-compose.yml` are still in the repo if you ever want the container route instead.

## Layout

```text
bot/       Telegram bot
server/    Shared DB, TMDB client, FastAPI
data/      SQLite file (created on first run)
```

## Database

SQLite file: `data/sofar.db` (path from `DATABASE_URL` in `.env`).

| Table | Purpose |
|-------|---------|
| `users` | Telegram identity (`telegram_id`) |
| `titles` | Cached TMDB movies/shows |
| `user_titles` | Your library row: status + season/episode |

Tables are created automatically on bot/API startup. No separate migration step for MVP.

Inspect locally:

```bash
sqlite3 data/sofar.db ".tables"
sqlite3 data/sofar.db "SELECT * FROM user_titles;"
```

## Notes

- Secrets stay in `.env` (gitignored).
- Adding the same TMDB title again updates status instead of duplicating.
- On startup the bot registers slash-commands with Telegram (type `/` in chat to see them).
- Phase 2 will add episode air alerts. Phase 3 is the PWA.
