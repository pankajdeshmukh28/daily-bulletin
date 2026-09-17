# Decisions — what got built, and why

A running record of what this project does, the product and technical
choices behind it, and why each one was made. Written for future sessions
(human or Claude) picking this back up without the original conversation.
See [README.md](README.md) for how to actually run things.

## What it is, in one paragraph

A personal research tool, not a trading bot: every weekday morning it reads
news + price action for the S&P 500 and Nifty 50, has Claude pick the most
interesting stocks/ETFs with a stated thesis, and delivers a digest to
Telegram and a web dashboard. Separately, it evaluates mutual funds on
standard risk/return statistics (std dev, beta, alpha, Sharpe, R²) with a
plain-English verdict alongside the numbers. It tracks every pick's actual
performance against the index and feeds that record back into the next
day's prompt, so the system is meant to get better calibrated over time,
not just repeat the same behavior forever.

## Timeline

- **2026-09-06/07** — Built from scratch: universe scraping (Wikipedia),
  price snapshots (`yfinance`), headline collection (Google News RSS, no
  API key), Claude analysis into ranked picks, Telegram delivery, pick
  tracking with a self-calibration feedback loop. Repo created and pushed
  2026-09-07 (`ca1247a`).
- **2026-09-07 (same day)** — Moved all persistence from git-committed
  JSON/JSONL files to a Turso database (`68fe790`), moved scheduling from
  local `launchd` to GitHub Actions, retired the local agents (`b77b16a`).
- **2026-09-08** — Repo made public at explicit user request. Considered
  scrubbing 2 early commits that still hold plaintext pick history from
  before the Turso migration; user said to drop that plan (2026-09-14) —
  left as-is, low-stakes (no credentials, no PII, just stock tickers).
- **2026-09-11** — First real production failure: the US digest didn't
  send because a heavy day's response exceeded the `max_tokens` budget.
  Caught via GitHub Actions logs, fixed same class of issue as the video
  pipeline's own `max_tokens` gotcha (`db98448`, 2026-09-14).
- **2026-09-16** — Two new features added in one day:
  1. Mutual fund evaluation (`99669e3`) — std dev/beta/alpha/Sharpe/R² for
     US and India funds.
  2. Web dashboard as a published Claude Artifact (`ff49af9`), plus
     same-day follow-up: plain-English fund explanations (`3c6f685`)
     after user feedback that raw stats meant nothing to non-quant users.
- **2026-09-17** — Fund Ledger UX reimagined for clutter (this document,
  `22e6b0d`) after user feedback that the evaluator, while functionally
  good, was too dense.

## Product decisions

**Scope: S&P 500 + Nifty 50, not "all stocks."** The user's two markets.
Kept as a fixed, curated universe (with a 7-day Wikipedia-scrape cache)
rather than trying to cover every listed stock — keeps headline-fetching
and Claude's context bounded and keeps the picks explainable.

**ETFs are in, mutual funds are a separate capability.** ETFs trade like
stocks (live price, can react to daily news), so they slot directly into
the daily digest's "buy candidates" format. Mutual funds price once a day
via NAV and settle over days — a "news today, act tomorrow" signal has no
edge there. Instead of forcing them into the same shape, they got their
own capability: standard risk/return statistics computed from historical
returns, which is the kind of analysis that actually fits how mutual funds
work (see "Mutual fund evaluation" below).

**Plain English *and* the real numbers, never one instead of the other.**
This came up twice, in two different parts of the product, both times as
explicit user correction:
- The daily digest's Telegram summary started out with explanatory
  sentences; the user said keep the summary compact, put the "why" in the
  attached report instead — and separately, make the avoid list actually
  explain *why not*, not just name tickers, with real investing
  vocabulary allowed ("earnings", "valuation") but not dense jargon
  ("re-rating", "multiple compression").
- The fund evaluator initially showed only raw stats (σ, β, α, Sharpe,
  R²) with no interpretation — useless to a non-quant reader. Fixed by
  adding a Claude-generated paragraph that ties all 5 numbers together
  *and explicitly uses R² to say how much to trust the others* — while
  keeping the raw figures visible, not replaced, for anyone who wants
  them directly.

Net rule now applied consistently: numbers stay visible for people who
want them; a plain-language explanation sits alongside, not gating access
to the numbers and not diluting them into nothing.

**Two web pages, not one, and the fund page starts empty.** The first
dashboard version put the whole curated fund leaderboard — 9+ funds, each
with a full stat grid and paragraph — on the same page as the daily stock
digest. User feedback: that's unrequested clutter on the page checked
daily for stock picks. Fix: split into **Daily Bull-etin** (digest +
scorecard only) and **Fund Ledger** (fund evaluation only), and — more
than just moving the section — Fund Ledger no longer preloads any curated
list at all. It starts empty; a fund only appears once someone has
actually asked for it. The curated weekly evaluation still runs in the
background (durable history in Turso), it just isn't dumped on either
page by default.

**Fund Ledger UX reimagined once, decisively.** Even after the split, the
evaluator itself was called "cluttered" (2026-09-17): a 4-field form
(market, ticker, *name*, submit), a standing paragraph defining all 5
terms before any action, and a boxy bordered 5-cell stat grid plus a
separate Sharpe badge per fund. Reworked to: one text field + a market
toggle + button (the name field was dropped entirely — resolved
automatically from `yfinance`/`mfapi.in` instead of asking the user to
type it), three clickable example chips so a first-time visitor isn't
staring at a blank field, the glossary collapsed behind a closed
`<details>`, and each fund rendered as a name + one-line monospace stat
strip (σ/β/α/Sharpe/R² with their real symbols, hover tooltips for the
plain-language caption) followed by the verdict paragraph — same
information, far less permanent visual weight.

**Repo is public.** Made public at explicit user request (2026-09-08).
Verified before and after that no secret ever touched git history — all
credentials are GitHub Actions secrets, encrypted regardless of repo
visibility, and the only things ever committed are code plus (briefly,
pre-Turso) non-sensitive pick history.

**GitHub Actions over a local machine.** The user's Mac isn't always on;
a scheduled job that needs 100% local uptime isn't viable. Moved
everything — daily digest, weekly fund refresh — to GitHub Actions, which
also means anyone (or any future session) can trigger a run by hand from
the Actions tab without touching a laptop.

## Technical decisions

**Turso (hosted SQLite) instead of committing data to git.** Originally,
runs, prices, and picks were written to JSON/JSONL files and committed
back to the repo by CI. Once the repo was headed toward public, that
became a privacy problem (daily picks visible to anyone), so all state
moved to a private Turso database — `db.py` — accessed over plain HTTP
rather than the `libsql-client` package, whose sync client was found to
hang/fail its websocket handshake against current Turso servers (a raw
HTTPS request to the same endpoint worked in under a second; confirmed
live, not assumed). Four tables: `runs` (health/error log),
`market_snapshot` (the day's index/movers/ETF prices — the raw evidence
fed to Claude), `picks` (every pick + entry price, append-only, used by
the self-calibration loop), `reports` (the full Claude output as JSON).
A fifth, `fund_metrics`, was added later via an idempotent `ALTER TABLE`
migration (the table already had live rows when the `explanation` column
was added).

**Self-calibration feedback loop.** Every day's prompt includes a summary
of the bot's own past pick performance — broken down by signal type
(momentum/dip_buy/catalyst/relative_strength) and by conviction level —
so the model can lean toward what's actually produced alpha instead of
repeating the same behavior regardless of results. An early, honestly
reported finding from this data: conviction-2 picks have consistently
*outperformed* higher-conviction picks (as of 2026-09-17: conviction 2
at −0.06% average alpha vs. index, conviction 5 at −4.02%, n=68 vs. n=6
— check `reports/scorecard.md` or the dashboard for current numbers, this
moves daily). Not acted on yet — the sample is still small and most
positions are only days old — but the loop is built specifically so this
kind of pattern gets surfaced rather than buried.

**Mutual fund evaluation: two different data sources, on purpose.** US
mutual funds trade with a real ticker (FXAIX, VTSAX, ...), so they reuse
the exact same `yfinance` path as stocks/ETFs. India mutual funds have no
ticker at all — evaluated via `mfapi.in`, a free, no-auth API serving
AMFI's official daily NAV history by scheme code. Both feed into the same
`compute_metrics()` — 3 years of daily returns against the market index,
annualized standard deviation/beta/alpha (Jensen's, vs. a risk-free rate:
live `^IRX` for the US, a hand-maintained RBI repo-rate constant for
India since no free live source was found)/Sharpe/R². Verified against a
textbook sanity check: an S&P 500 index fund evaluated against the S&P
500 itself comes back with beta ≈ 1.00 and R² ≈ 99.9%. Every evaluation
is appended (not overwritten) to `fund_metrics`, so metrics-over-time is
queryable later even though nothing currently visualizes that yet.

**Claude Artifacts instead of a real hosted backend.** A published
Artifact page's script tags can load from a small CDN allowlist but
cannot `fetch()` an arbitrary external API — meaning a static Artifact
page has no way to call the project's own Turso database live. Two paths
were on the table: (a) build and deploy a real backend service so the
dashboard updates automatically, or (b) accept a manually-refreshed
snapshot plus the Artifact `db` capability (its own small built-in
database) for anything that needs to be genuinely interactive. Given the
choice directly, the user picked (b) — see "the fund evaluator is
asynchronous by design" below for what that trades away.

**The fund evaluator is asynchronous by design, not a bug.** Because a
static page can't run Python/call `yfinance`/call Claude on its own, "type
a fund, get an instant real answer" isn't achievable without a real
backend. What *is* achievable, and what's built: a viewer's request is
written to the Artifact's own `db` capability as `pending`; a Claude
session with access to this project (asked by the user, or run
periodically) processes pending requests by actually running
`evaluate_funds.py` and writes the real result back; every open browser
tab updates live via `onSnapshot`, no page reload or republish needed.
This was a deliberate choice to be honest about the constraint rather
than fake a live tool with hardcoded or hallucinated numbers.

**Shared Claude-response helpers factored out (`claude_client.py`).**
Both the digest analysis and the fund explanations hit the same two
gotchas: `claude-sonnet-5` can emit a `ThinkingBlock` before the actual
text block (so code must search by `block.type == "text"`, never assume
`content[0]`), and thinking tokens eat into the `max_tokens` budget
(caused a real production failure once — see 2026-09-11 above). Pulled
into one module so a future third caller doesn't have to relearn either
gotcha.

## Known limitations / not built

- **India's risk-free rate is a hand-maintained constant**, not a live
  feed — no free live source was found. Needs occasional manual updates
  as RBI's repo rate changes.
- **The web dashboard is manually refreshed**, not live — accepted
  tradeoff, see above. A real hosted backend would remove this but wasn't
  built (explicitly deprioritized when offered).
- **2 early git commits still hold non-sensitive plaintext pick history**
  from before the Turso migration. Scrub was planned, then explicitly
  dropped by the user (2026-09-14) — not an oversight, a decision.
- **YouTube-style "curated fund leaderboard" browsing UI doesn't exist**
  — `fund_metrics` accumulates real history in Turso, but nothing
  surfaces "how has our curated list done over time" yet. Natural next
  step if the fund evaluator gets used enough to want it.
- **No mutual-fund investment advice, only risk profiling** — the
  explanations are deliberately scoped to never issue a buy/sell call;
  this is a design constraint, not a missing feature.
