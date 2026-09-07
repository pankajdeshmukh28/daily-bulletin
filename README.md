# Stock Signal Bot

Daily news-driven directional digest for the **S&P 500 (US)** and **Nifty 50
(India)**. For each market it:

1. Loads the index constituents (scraped from Wikipedia, cached 7 days —
   `universe.py`).
2. Batch-downloads recent prices via `yfinance` and finds the biggest 1-day
   movers in both directions (`prices.py`).
3. Pulls macro headlines + per-mover headlines from Google News RSS — no news
   API key needed (`news.py`).
4. Has Claude (`claude-sonnet-5`) digest it into ranked **buy candidates**
   with conviction (1–5), thesis, catalysts, risks, and horizon, plus a
   watchlist and an avoid list (`analyze.py`).
5. Writes `reports/<date>_<market>.md` (human) and `.json` (raw).
6. Logs each pick + entry price to `data/picks_log.jsonl` (`track.py`) and
   sends a summary message + the full report to Telegram (`notify.py`) via
   the dedicated **Daily Bull-etin** bot (`@daily_bulletin_stocks_bot`,
   token + private chat id in this project's `.env`); skip with
   `--no-telegram`.

It generates research signals only — it does **not** place trades, and its
output is informational, not financial advice.

## Run

```
cd passive-apps/stock-signal-bot
.venv/bin/python run_daily.py            # both markets
.venv/bin/python run_daily.py --market us
.venv/bin/python run_daily.py --market india
```

Needs `ANTHROPIC_API_KEY` — read from `.env` here, falling back to
`toddler-video-pipeline/.env` (already set on this machine).

Venv (Python 3.12 — the macOS system python3 is 3.9 and too old):

```
/opt/homebrew/opt/python@3.12/libexec/bin/python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Tuning

`config.py`: number of movers scanned, headlines per query, number of picks,
macro news queries per market, model.

## Performance tracking + feedback loop

```
.venv/bin/python track.py
```

Grades every logged pick against current prices and the index over the same
window (alpha), broken down by signal type (`momentum`, `dip_buy`,
`catalyst`, `relative_strength`) and by conviction level, and writes
`reports/scorecard.md`. Runs automatically after the scheduled US run.

The track record also feeds back into the daily analysis: each run injects
a summary of past pick performance (overall, by signal type, by conviction,
plus recent picks) into the Claude prompt, so the model calibrates toward
what has actually produced alpha and explicitly flags repeat picks.
Rows logged before signal types existed show as `untagged`.

## Scheduling (GitHub Actions)

`.github/workflows/daily.yml` runs the digests in the cloud so no local
machine needs to be on:

- **US**: Mon–Fri 12:45 UTC (5:45 AM PDT / 4:45 AM PST) — before NYSE opens.
- **India**: Mon–Fri 02:30 UTC (8:00 AM IST) — before NSE opens at 9:15 IST.
- Manual: Actions tab → "Daily Bull-etin" → Run workflow (pick market).

Each run commits `data/` (pick log — the model's self-calibration memory)
and `reports/` back to the repo, so state persists across ephemeral runners.
Secrets required on the repo: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`.

The old local launchd agents in `scheduling/` are retired — if they're
still loaded, remove with `launchctl bootout gui/$(id -u)/com.pankaj.stock-signal-us`
(same for `-india`).

## Not built yet / ideas

- Nifty 100 / broader universes (one URL change in `universe.py`).
- Sizing/portfolio logic — currently pure directional signals.
