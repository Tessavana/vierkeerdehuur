# 4xIncomeNoKeys

Simple first architecture for Eindhoven housing search:

1. Scrape listings (Pararius URL based)
2. Filter by your hard rules
3. Deduplicate in SQLite
4. Score matches
5. Send instant alerts (console + optional Telegram)

## Quick start

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env`.

The default config uses `file://data/sample_listings.json` so the pipeline is verifiable immediately.

3. Run one scan:

```bash
python main.py --once
```

4. Run continuously:

```bash
python main.py
```

## Current scope

- Rental flow for Eindhoven (direct sources: Pararius, Funda huur, VB&T, Vesteda, Rotsvast, NMG, Huurwoningen, Kamernet, Huislijn, Rentfinder)
- GitHub Pages dashboard (`docs/`) with map, countdown to 26 July 2026, and match tags (`meh` → `super nice`)
- Listing lifecycle: removed when no longer on source sites; orange highlight for listings first seen today

See `docs/TAG_METRICS.md` for how tags are scored.

### GitHub Actions (free tier friendly)

Two workflows share one cache and cancel overlapping runs:

| Workflow | Schedule | What it does | ~minutes |
|----------|----------|--------------|----------|
| **Housing Scan (fast)** | every 12 min | Pararius, Rotsvast API, VB&T XML, Kamernet, etc. | ~2 min |
| **Housing Scan (full)** | every 2 hours | Funda, NMG, Huurwoningen, Vesteda (Playwright) + Telegram | ~8 min |

**Private repos:** ~2000 Actions minutes/month → this mix uses ~**900–1100 min/month** (headroom left).

**Public repos:** unlimited minutes; fast scans can run even more often (edit cron in `housing-scan-fast.yml`).

### Funda / NMG (Playwright)

If Funda returns zero listings (bot wall), bootstrap a browser session:

```bash
python -m src.session_bootstrap --url "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D" --wait-seconds 120
```

## Real source mode (optional now)

Change `SEARCH_URLS` to a real site URL, for example:

`SEARCH_URLS=https://www.pararius.com/apartments/eindhoven`

If a source blocks direct requests, the run continues and other providers still execute.

If `ENABLE_PLAYWRIGHT_FALLBACK=true`, blocked pages are retried with headless Chromium.
For stricter anti-bot sites, use a persisted browser session (no cookie copy in `.env`):

1. `.\.venv\Scripts\python -m playwright install chromium`
2. `.\.venv\Scripts\python -m src.session_bootstrap --url "https://www.pararius.com/apartments/eindhoven" --wait-seconds 120`
3. Finish challenge/login in opened browser window
4. Session state is saved to `data/playwright_state.json` and reused automatically

## Telegram alerts

Set in `.env`:

- `TELEGRAM_ENABLED=true`
- `TELEGRAM_BOT_TOKEN=...`
- `TELEGRAM_CHAT_ID=...`

The app will still print to console and additionally send Telegram messages.

## GitHub Actions every 5 minutes

Workflow file: `.github/workflows/housing-scan.yml`

Required repository secrets:

- `SEARCH_URLS` (comma-separated URLs)
- `MAX_RENT` (example: `1150`)
- `MIN_SIZE` (example: `20`)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

The workflow now also builds `docs/data/latest_listings.json` and deploys `docs/` to GitHub Pages.

## Localhost status page

Run:

`python main.py --status-server --port 8080`

Then open `http://127.0.0.1:8080` to view:

- scraper/database status
- telegram config status
- github workflow presence
- recent event log (provider failures, alerts sent, telegram failures)

## GitHub hosted website (clean UI)

Static site files live in `docs/`.

- Main page: `docs/index.html`
- UI styles: `docs/styles.css`
- Data feed: `docs/data/latest_listings.json`

After enabling GitHub Pages (Source: GitHub Actions), each scheduled run updates the website with the latest Eindhoven listing workrun.

### Telegram feedback commands for application tracking

Send commands to your bot in the same chat used for alerts:

- `/applied <address>`
- `/viewing <address>`
- `/rejected <address>`
- `/noresponse <address>`

These commands are synced into `data/application_status.json` and shown in the hosted dashboard overview.

On GitHub Actions, `data/listings.db`, `data/application_status.json`, and `data/telegram_offset.txt` are cached between runs, so:

- repeated matches are not re-notified every run
- Telegram status commands are remembered across scheduled runs
