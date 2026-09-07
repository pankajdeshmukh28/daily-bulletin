"""Price snapshots via yfinance: last close, 1-day and 5-day % change."""

import math

import yfinance as yf


def snapshot(tickers: list[str]) -> dict[str, dict]:
    """Batch-download ~2 weeks of dailies; return per-ticker stats.

    Tickers with missing/partial data are silently dropped — with 500 names
    there is always a handful of delisted/renamed symbols.
    """
    data = yf.download(
        tickers,
        period="15d",
        interval="1d",
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=True,
    )
    out = {}
    for t in tickers:
        try:
            closes = data[t]["Close"].dropna()
        except KeyError:
            continue
        if len(closes) < 6:
            continue
        last, prev, week_ago = closes.iloc[-1], closes.iloc[-2], closes.iloc[-6]
        if any(math.isnan(x) or x == 0 for x in (last, prev, week_ago)):
            continue
        out[t] = {
            "close": round(float(last), 2),
            "pct_1d": round(float(last / prev - 1) * 100, 2),
            "pct_5d": round(float(last / week_ago - 1) * 100, 2),
        }
    return out


def index_snapshot(index_ticker: str) -> dict | None:
    snap = snapshot([index_ticker])
    return snap.get(index_ticker)


def top_movers(snap: dict[str, dict], per_direction: int) -> list[str]:
    """Tickers with the largest 1-day moves, both directions, gainers first."""
    ranked = sorted(snap, key=lambda t: snap[t]["pct_1d"], reverse=True)
    gainers = ranked[:per_direction]
    losers = [t for t in reversed(ranked[-per_direction:]) if t not in gainers]
    return gainers + losers
