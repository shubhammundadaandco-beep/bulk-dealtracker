# Bulk/Block Deal Watchlist Tracker

Tracks NSE & BSE bulk/block deals daily, flags deals by a watchlist of investors
(known + lesser-known), sends Telegram alerts, and logs full history for later
analysis.

## ⚠️ Read this before relying on it

- NSE and BSE do not publish an official public API for bulk/block deals.
  This tool uses **unofficial, reverse-engineered endpoints** that community
  developers have documented. They can change or break **without notice**.
- I built this without live network access to nseindia.com or bseindia.com,
  so **I have not been able to test-execute these scrapers against the real
  sites**. You must test this yourself, on a normal internet connection,
  before trusting any alert it sends.
- The BSE endpoint/field names in `scraper_bse.py` are the least certain part
  of this build — treat them as a starting point to debug, not as verified fact.
- If NSE/BSE blocks requests (403, captcha, empty response), the code is
  written to fail loudly (raise + send a Telegram failure alert) rather than
  silently return zero deals — but you should still spot-check manually for
  the first few weeks.

## What it does

1. `scraper_nse.py` — fetches today's bulk deals, block deals, and short-selling
   data from NSE.
2. `scraper_bse.py` — fetches today's bulk/block deals from BSE.
3. `matcher.py` — fuzzy-matches deal "client name" fields against your
   `watchlist.json`, using `rapidfuzz`.
4. `notifier.py` — sends Telegram messages for watchlist hits, a daily summary,
   and failure alerts.
5. `main.py` — orchestrates the above, logs every deal (not just hits) to
   `data/history.csv` for later analysis (e.g. finding recurring non-watchlisted
   names worth promoting to the watchlist).
6. `.github/workflows/daily-check.yml` — runs `main.py` on a daily cron via
   GitHub Actions, commits the updated history file back to the repo.

## Setup

### 1. Create a Telegram bot
1. Open Telegram, message **@BotFather**, send `/newbot`, follow prompts.
2. Save the bot token it gives you.
3. Message your new bot once (anything), then visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser to find
   your `chat_id` in the JSON response (`message.chat.id`).

### 2. Install dependencies locally (for testing)
```bash
pip install -r requirements.txt
```

### 3. Configure
- Edit `watchlist.json` — add/remove investor names.
- Set environment variables (locally, or as GitHub Secrets for Actions):
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`

### 4. Test locally BEFORE relying on automation
```bash
python main.py
```
Check the console output and your Telegram chat. Debug scraper issues here —
do not deploy to GitHub Actions until this works locally.

### 5. Deploy to GitHub Actions
1. Push this repo to GitHub (private repo recommended, since history.csv will
   contain data you're tracking).
2. In repo Settings → Secrets and variables → Actions, add
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repository secrets.
3. The workflow in `.github/workflows/daily-check.yml` will run on the
   schedule defined there (edit the cron expression to your preferred IST time —
   GitHub Actions cron is in UTC, so convert accordingly).
4. You can also trigger it manually from the Actions tab (`workflow_dispatch`)
   to test end-to-end before trusting the schedule.

## Known gaps / next steps (not built yet, per our scoping discussion)
- Post-deal price performance tracking (1-day/1-week/1-month return after a
  flagged deal).
- Web dashboard (Telegram-only for now).
- AI-generated plain-English daily summary (optional, cosmetic).

## Files
```
bulk-deal-tracker/
├── main.py                          # orchestrator
├── scraper_nse.py                   # NSE bulk/block/short-sell scraper
├── scraper_bse.py                   # BSE bulk/block scraper (least verified)
├── matcher.py                       # fuzzy watchlist matching
├── notifier.py                      # Telegram alerts
├── watchlist.json                   # your tracked investor names
├── requirements.txt
├── data/
│   └── history.csv                  # created on first run
└── .github/workflows/
    └── daily-check.yml              # GitHub Actions cron job
```
