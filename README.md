# Sofar

Personal movie and TV tracker. A Telegram bot and an installable web app (PWA), both on the same backend and database.

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

### Run the web app locally

Two terminals - the API and the Vite dev server:

```bash
# terminal 1
uvicorn server.api:app --reload --port 8000

# terminal 2
cd web
npm install
npm run dev          # http://localhost:5173
```

Vite proxies `/api` to port 8000, so both work with no extra config. Log in by
sending `/app` to your bot and typing the 6-character code.

### Tests

```bash
pytest
```

## Bot commands

| Command | What it does |
|---------|----------------|
| `/start` | Home: Search · Continue · My list |
| `/search` | Live search (or `/search the bear` fallback) |
| `/list [want\|watching\|watched]` | Your library |
| `/next` / `/watched` | Continue watching |
| `/app` | Get a login code for the web app |
| `/cancel` | Cancel season/episode prompt |
| `/help` | Quick tips |

Status words are always **Want · Watching · Watched**. Episode action is **Mark ep**.

### Live search (inline mode)

1. In [@BotFather](https://t.me/BotFather), send `/setinline` for your bot.
2. Placeholder example: `movie or show…`
3. Tap **Search** in Sofar and type.

Filters while typing: `movie dune`, `tv the bear` (or `m:` / `t:`).

## Web app

An installable PWA that reads and writes the same library as the bot.

- **Library** tab: filter by All / Want / Watching / Watched
- **Search** tab: type-ahead TMDB search, tap a result to add it
- Tap any title for a detail sheet: change status, step season/episode, mark an
  episode watched, or remove it
- Works on a phone home screen; posters are cached for offline browsing

### How login works

There are no passwords. The bot is the identity provider:

1. Send `/app` to the bot - it returns a 6-character code, good for 10 minutes.
2. Enter the code in the web app.
3. The app trades it for a long-lived token kept in `localStorage`.

Codes are single use. **Sign out** revokes the token on the server.

## Deploy on a VPS (systemd, no Docker)

Full server notes (SSH alias, Cockpit, specs, backups): see **[docs/vps.md](docs/vps.md)**.

The bot uses long polling, so **no inbound ports** are required. The VM only needs outbound HTTPS to Telegram and TMDB, and it idles at roughly 60-90 MB of RAM.

### 1. Clone and configure

```bash
sudo apt update && sudo apt install -y git python3-venv
git clone https://github.com/uhohnelson/so-far.git sofar
cd sofar
cp .env.example .env
nano .env   # set TELEGRAM_BOT_TOKEN and TMDB_API_KEY
```

### 2. Install the services

```bash
bash deploy/setup.sh              # bot + web app
bash deploy/setup.sh --bot-only   # skip the web app
```

This creates a venv, installs dependencies, adds a 1 GB swapfile if none exists,
installs Node 22 and builds `web/dist` (unless `--bot-only`), then installs and
starts two systemd units that restart on crash and on reboot:

| Unit | What it runs |
|------|--------------|
| `sofar-bot` | the Telegram bot (long polling) |
| `sofar-web` | uvicorn on `127.0.0.1:8000`, serving the API and the PWA |

### 3. Put HTTPS in front of the web app

`sofar-web` listens on localhost only. A PWA needs HTTPS, so terminate TLS with
Caddy - it gets certificates automatically:

```bash
sudo apt install -y caddy
sudo nano /etc/caddy/Caddyfile
```

```caddyfile
sofar.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

```bash
sudo systemctl restart caddy
```

Open **80** and **443** in your Oracle security list and in the VM firewall
(`sudo ufw allow 80,443/tcp`). Point your domain's A record at the VPS IP first,
or Caddy cannot issue a certificate.

Then tell the bot where the app lives, so `/app` includes the link:

```bash
nano .env                      # WEB_APP_URL=https://sofar.example.com
sudo systemctl restart sofar-bot
```

### 4. Useful commands

```bash
journalctl -u sofar-bot -f          # bot logs
journalctl -u sofar-web -f          # web/API logs
sudo systemctl restart sofar-web
bash deploy/update.sh               # pull, rebuild web, restart both
```

The SQLite file lives at `data/sofar.db` inside the checkout, so back it up with `cp` or `scp`.

### 5. Optional: seed your existing library

From your Mac, after the services have run once:

```bash
ssh you@YOUR_VPS_IP 'sudo systemctl stop sofar-bot sofar-web'
scp data/sofar.db you@YOUR_VPS_IP:~/so-far/data/sofar.db
ssh you@YOUR_VPS_IP 'sudo systemctl start sofar-bot sofar-web'
```

Or start empty on the VPS and re-add titles - fine for MVP.

### Notes

- Works on Oracle Always Free Ampere (ARM); the Python side is arch-independent and Node 22 has arm64 builds.
- The bot needs **egress only**. The web app needs inbound **80/443** for HTTPS.
- Keep only **one** bot process running (stop your Mac bot before going live on the VPS, or Telegram will conflict).
- `Dockerfile` / `docker-compose.yml` are still in the repo if you ever want the container route instead.

## Layout

```text
bot/       Telegram bot
server/    Shared DB, TMDB client, FastAPI
web/       React PWA (Vite) - built into web/dist
tests/     API tests
deploy/    systemd units and setup scripts
data/      SQLite file (created on first run)
```

The API serves `web/dist` when it exists, so one process serves both the API and
the web app in production.

## Database

SQLite file: `data/sofar.db` (path from `DATABASE_URL` in `.env`).

| Table | Purpose |
|-------|---------|
| `users` | Telegram identity (`telegram_id`) |
| `titles` | Cached TMDB movies/shows |
| `user_titles` | Your library row: status + season/episode |
| `login_codes` | Short-lived `/app` codes (10 min, single use) |
| `api_tokens` | Web app bearer tokens |

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
- Web tokens are bearer tokens in `localStorage`; `/app` codes expire after 10 minutes and work once.
- Still to come: episode air alerts (Phase 2) and a custom 404 page for the web app.
