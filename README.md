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

- Rental flow only
- File provider (for local verification) and Pararius provider
- Console notifications only

This is intentional for MVP stability. Next features can be added one by one (FastAPI dashboard, Funda buy flow, richer scoring).

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
