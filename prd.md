# PRD - Sofar MVP

## Summary

Sofar helps you track what you watch - movies and TV shows - so you always know where you left off and what is next.

It starts as a Telegram bot (fast to ship). Later it grows into a web app (PWA) that shares the same backend.

Sofar is a personal tracker and notifier. It is not a download or streaming service.

## Product Goal

Replace the core of TV Time for personal use: search titles, add them to a list, mark progress, see what is next, and get notified when new episodes air.

## Name

- Product: **Sofar** (as in "so far" - what you have watched so far)
- Suggested Telegram bot: `@sofar_bot` or `@sofarwatch_bot` (confirm availability)
- Suggested web later: `sofar.app` or similar (confirm availability)

## Users

### You (primary)

- Track your own movies and shows
- Use Telegram daily for quick logging
- Want alerts for new episodes

### Friends (later, optional)

- Same bot, their own private lists
- No shared social feed in MVP

## Success Metrics

- Add a title from search to list in under 30 seconds
- Mark an episode watched in under 10 seconds (bot flow)
- New-episode alerts arrive within 24 hours of air date (MVP) and ideally within a few hours later
- Zero confusion between "watching", "watched", and "want to watch"
- You still use Sofar after 2 weeks instead of a notes app

## Non-Goals (MVP)

Sofar MVP will not include:

- Downloading, torrents, or streaming links
- Social feed, friends activity, or public profiles
- Reviews, ratings community, or comments
- Live TV / sports scores
- Multi-profile households (kids vs adults) beyond one account per Telegram user
- Perfect offline PWA features on day one (PWA comes after bot)
- Import from every tracker under the sun (TV Time import can be a later stretch)

## Assumptions

- Metadata comes from a public API (preferred: TMDB). You will need an API key.
- Episode air dates from the metadata provider are "good enough" for alerts.
- Telegram user id is enough identity for MVP (no email login yet).
- One repo holds bot now and web later, with a shared server and database.
- You are fine hosting this yourself (Mac for early testing, VPS later if you want 24/7 alerts).

## Product Principles

1. Fast logging beats fancy UI at the start.
2. One source of truth for lists and progress.
3. Bot and web share the same API - never two databases.
4. Track watching only - never become a pirate index.
5. Simple English in the product copy. Prefer hyphens over em dashes.

## Scope

### Phase 1 - Telegram bot (ship first)

Core features:

- `/start` - short welcome and how to use Sofar
- `/search <query>` - search movies and TV shows (TMDB)
- Pick a result - add to list with status:
  - Want to watch
  - Watching
  - Watched
- For TV shows:
  - Set or update current season + episode
  - `/next` - show what is next to watch
  - `/watched` - mark current episode done and advance
- `/list` - show your lists (filter by status)
- `/remove` - remove a title from your list
- Basic title detail in chat (year, type, poster thumbnail if Telegram allows, overview short)

Nice-to-have in Phase 1 if time allows:

- Inline search results with buttons
- `/watching` shortcut list
- Deduplicate: adding the same TMDB id twice updates status instead of creating a second row

### Phase 2 - Episode alerts

- Background job checks air dates for shows marked Watching
- Telegram message when a new episode is out (or scheduled for today)
- Mute per show

### Phase 3 - Web PWA

- Same account via Telegram login (or link code) so lists sync
- Browse posters, seasons, and history
- Installable PWA for phone home screen
- Deep links from bot messages into the web title page

## User Flows

### Add a show (bot)

```text
User
  |
/search the bear
  |
Bot shows results (buttons)
  |
User taps a show
  |
Bot asks status: Want / Watching / Watched
  |
If Watching: ask season + episode (or default S1E1)
  |
Saved to user library
```

### Mark progress (bot)

```text
User
  |
/watched
  |
Bot uses "currently watching" show
  or asks which show
  |
Marks episode watched
  |
Advances to next episode if known
  |
Confirms: "Marked S2E4. Next up: S2E5 - Title"
```

### New episode alert (Phase 2)

```text
Scheduler
  |
Checks Watching shows
  |
Finds newly aired episode
  |
Sends Telegram DM
  |
User can tap Mark watched or Open details
```

## Data Model (MVP sketch)

### User

- id
- telegram_id (unique)
- display_name (optional)
- created_at
- timezone (optional, for alert timing)

### Title

- id
- tmdb_id
- media_type (movie | tv)
- title
- year
- poster_path
- overview (short)
- cached metadata JSON (optional)
- updated_at

### UserTitle (library row)

- id
- user_id
- title_id
- status (want | watching | watched)
- current_season (tv only, nullable)
- current_episode (tv only, nullable)
- rating (optional later)
- notes (optional later)
- created_at
- updated_at

### WatchEvent (optional but useful)

- id
- user_id
- title_id
- season
- episode
- watched_at

### AlertPref (Phase 2)

- user_id
- title_id
- muted (bool)

## Tech Direction

### Suggested stack (can change at build time)

- Server: Python (FastAPI) or Node - pick what you ship faster with
- DB: SQLite first, Postgres if you need multi-device sync hard
- Bot: python-telegram-bot or grammY / telegraf
- Metadata: TMDB API
- Jobs: cron or APScheduler for episode checks
- Web later: Next.js or Vite PWA against the same API

### Repo layout (one repo)

```text
sofar/
  prd.md
  apps/
    bot/
    web/          # Phase 3
  packages/       # or server/
    api/
    db/
```

Flatter is fine at the start:

```text
sofar/
  prd.md
  bot/
  server/
  web/            # later
```

## API Surface (shared)

Minimum endpoints the bot (and later web) need:

- Search titles
- Get title detail (and TV seasons/episodes)
- List user library
- Add / update library row
- Mark episode watched / set progress
- Remove from library
- (Phase 2) List due alerts / mark alert sent

## Risks

- TMDB rate limits or key issues
- Air dates wrong or timezone messy - alerts feel late or early
- Telegram message limits for long lists - need paging
- Scope creep into social or download features
- Building PWA too early before bot habits stick

## Open Questions

1. Bot username and domain: lock Sofar handles early.
2. Timezone: default to a fixed zone first, or ask on `/start`?
3. Movies: does "watched" mean finished once, or allow rewatch tracking in MVP?
4. Multi-show "currently watching": allow many Watching shows, or one primary?
5. TV Time import: worth a Phase 2 stretch, or ignore forever?

## Launch Checklist (Phase 1)

- [ ] Create Telegram bot via BotFather
- [ ] TMDB API key in `.env` (never commit secrets)
- [ ] Database migrations for User / Title / UserTitle
- [ ] Search + add + list + progress commands working
- [ ] Custom 404 N/A for bot-only; when web ships, add custom 404 before first web push
- [ ] README with setup steps
- [ ] Private GitHub repo when ready

## Out of Scope Reminder

If a feature helps pirates find files, it does not belong in Sofar. Point people at legal streaming info only if you add that later as metadata - never download links.
