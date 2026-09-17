# Stock Signal Bot

**Live pages:** [Daily Bull-etin](https://claude.ai/code/artifact/cfc086ce-f8a4-4996-aa33-236b0a10b35a)
(daily digest + scorecard) · [Fund Ledger](https://claude.ai/code/artifact/8dd634da-39b4-4aa5-9eb4-0d37726d9b5e)
(mutual fund evaluator). See [DECISIONS.md](DECISIONS.md) for the full
history of what's been built and why.

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
5. Writes `reports/<date>_<market>.md` locally for convenience (git-ignored —
   not the source of truth, see Database below).
6. Records the run, the day's market snapshot, every pick + entry price, and
   the full digest into a Turso (hosted SQLite) database (`db.py`), and sends
   a summary message + the full report to Telegram (`notify.py`) via the
   dedicated **Daily Bull-etin** bot (`@daily_bulletin_stocks_bot`, token +
   private chat id in this project's `.env`); skip with `--no-telegram`.

It generates research signals only — it does **not** place trades, and its
output is informational, not financial advice.

## Mutual fund evaluation

Mutual funds don't fit the daily news-signal model (NAV prices once a day,
no intraday responsiveness — see the "why not mutual funds" discussion this
project's history), but they're where most actual investing happens, so
there's a separate, complementary capability: risk/return evaluation using
the five standard quant metrics — **standard deviation, beta, alpha, Sharpe
ratio, R-squared** — computed from daily returns over a 3-year window
against the market benchmark (`mutual_funds.py`).

Data sources (funds have no unified price feed the way stocks do):
- **US**: funds trade with a real ticker (FXAIX, VTSAX, ...) — same
  `yfinance` path as stocks/ETFs.
- **India**: no ticker exists at all — uses [mfapi.in](https://www.mfapi.in/),
  a free, no-auth API serving AMFI's official daily NAV history by scheme
  code.

```
.venv/bin/python evaluate_funds.py --market us              # curated list
.venv/bin/python evaluate_funds.py --market india
.venv/bin/python evaluate_funds.py --market us --fund FXAIX --name "Fidelity 500 Index"
.venv/bin/python evaluate_funds.py --market india --search "quant small cap"   # find a scheme code
.venv/bin/python evaluate_funds.py --market india --fund 120828 --name "Quant Small Cap Fund"
```

Every evaluation (curated or one-off) is appended to the `fund_metrics`
table in Turso — history is kept, not overwritten, so metrics-over-time
becomes queryable later. Curated lists live in `config.py`
(`MARKETS[market]["mutual_funds"]`). The weekly `funds` job in
`daily.yml` (Sundays) refreshes the curated list automatically — risk
metrics don't meaningfully change day to day, so this doesn't need the
daily cadence the stock digest does.

Sanity-checked live: an S&P 500 index fund evaluated against the S&P 500
itself correctly comes back with beta ≈ 1.00 and R² ≈ 99.9%.

Every evaluation also gets a **plain-English verdict** (`explain_fund` in
`mutual_funds.py`, via Claude) that makes sense of all 5 numbers together
for a non-quant reader — and, critically, uses R² to say how much to
*trust* the beta/alpha reading, not just report it as a number. The raw
figures stay visible alongside it, not replaced — this was explicit user
feedback: the evaluator needs to work for everyday users without losing
the detail seasoned users want. `claude_client.py` holds the shared
Claude-response helpers (ThinkingBlock-safe text extraction, JSON-fence
stripping, max_tokens truncation check) used by both this and `analyze.py`.

## Web dashboard — two pages

Two separately published Claude Artifacts, split on explicit user feedback
that the fund evaluator's detail (5 stats + a paragraph per fund) was too
much unrequested content on the page you check daily for stock picks:

- **Daily Bull-etin** (`scripts/dashboard_template.html` →
  `scripts/dashboard.html`) — the latest digest for both markets and the
  real performance scorecard (including the conviction-vs-alpha chart that
  surfaced the conviction-inversion finding). No fund content beyond a
  one-line teaser linking to the second page. No `db` capability needed —
  purely a static snapshot.
- **Fund Ledger** (`scripts/fund_ledger.html`, hand-authored — no data to
  embed, so no render step) — the mutual fund evaluator, on its own page.
  **Starts empty.** A fund only appears here once someone has actually
  requested it through the form; there's no preloaded curated list.

Both are *manually refreshed* snapshots, not live-updating — a published
Artifact page can't call our own Turso API directly (the sandbox's
script-only CDN allowlist blocks arbitrary `fetch`). To refresh the digest:

```
.venv/bin/python scripts/render_dashboard.py   # pulls fresh Turso data into scripts/dashboard.html
```

then republish `scripts/dashboard.html` to its Artifact URL (Fund Ledger
needs no data refresh — it's pure live interaction).

The **fund evaluator is genuinely interactive** via the Artifact `db`
capability: a viewer submits a fund → written to a `requests` collection
as `pending` → ask Claude (in a session with access to this project) to
process pending requests → Claude runs `evaluate_funds.py` and writes the
result back → every open viewer sees it update live via `onSnapshot`, no
republish needed. This is asynchronous by design, not instant — there's no
way for a static page to run real computation on demand, so the honest
design is "request now, computed next time someone's here to fulfill it,"
not a fake instant answer.

Design: "ink ledger" theme — Fraunces (display) + Archivo (body) + IBM Plex
Mono (tabular data), deep ink-indigo accent kept separate from the
semantic green/red gain/loss colors, dark mode fully implemented. Both
pages share the same token system (duplicated — each Artifact is a fully
self-contained document, no shared stylesheet between them).

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

## Database (Turso)

All durable state — run history, the day's market snapshot (index/movers/
ETFs), every pick with entry price, and the full digest content — lives in a
private Turso (hosted SQLite/libSQL) database (`db.py`), not in the repo.
This means the repo can safely be made public: nothing about what the bot
picks, or how it's performed, is visible in git history or file listings.

`db.py` talks to Turso's plain HTTP pipeline API directly via `requests`
rather than the `libsql-client` package — that package's sync client hangs/
fails its websocket handshake against current Turso servers; the raw HTTP
API works cleanly and needs no extra dependency.

Needs `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN` (in `.env` locally, repo
secrets in CI). To set up your own:

```
brew install tursodatabase/tap/turso
turso auth login
turso db create daily-bulletin
turso db show daily-bulletin --url      # -> TURSO_DATABASE_URL
turso db tokens create daily-bulletin   # -> TURSO_AUTH_TOKEN
```

`scripts/migrate_to_db.py` is the one-time migration that moved the original
JSONL/JSON-file history into the DB — not needed again unless rebuilding
from scratch.

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

State persists in the Turso DB (see above), not via git commits — each
ephemeral runner reads/writes the same remote DB, so no commit-back step is
needed and the repo's file listing never changes day to day. Secrets
required on the repo: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`.

The old local launchd agents are retired — if any are still loaded, remove
with `launchctl bootout gui/$(id -u)/com.pankaj.stock-signal-us` (same for
`-india`).

## Not built yet / ideas

- Nifty 100 / broader universes (one URL change in `universe.py`).
- Sizing/portfolio logic — currently pure directional signals.
