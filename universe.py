"""Fetch and cache the stock universes (S&P 500, Nifty 50).

Constituents are scraped from Wikipedia and cached locally for 7 days so a
Wikipedia hiccup never blocks a daily run (the stale cache is used instead).
"""

import io
import json
import time

import pandas as pd
import requests

from config import DATA_DIR

CACHE_TTL_SECONDS = 7 * 24 * 3600
_HEADERS = {"User-Agent": "stock-signal-bot/0.1 (personal research tool)"}

_SOURCES = {
    "us": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "symbol_col": "Symbol",
        "name_col": "Security",
        # Yahoo uses '-' where the index list uses '.' (BRK.B -> BRK-B).
        "symbol_fixup": lambda s: s.replace(".", "-"),
    },
    "india": {
        "url": "https://en.wikipedia.org/wiki/NIFTY_50",
        "symbol_col": "Symbol",
        "name_col": "Company name",
        "symbol_fixup": lambda s: s + ".NS",
    },
}


def _cache_path(market: str):
    return DATA_DIR / f"universe_{market}.json"


def _scrape(market: str) -> list[dict]:
    src = _SOURCES[market]
    resp = requests.get(src["url"], headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    for table in pd.read_html(io.StringIO(resp.text)):
        if src["symbol_col"] in table.columns and src["name_col"] in table.columns:
            rows = [
                {
                    "ticker": src["symbol_fixup"](str(r[src["symbol_col"]]).strip()),
                    "name": str(r[src["name_col"]]).strip(),
                }
                for _, r in table.iterrows()
                if pd.notna(r[src["symbol_col"]]) and pd.notna(r[src["name_col"]])
            ]
            if len(rows) >= 40:  # sanity: both indices have >= 50 members
                return rows
    raise RuntimeError(f"Could not find constituents table at {src['url']}")


def get_universe(market: str) -> list[dict]:
    """Return [{ticker, name}, ...] for the market, cached for 7 days."""
    cache = _cache_path(market)
    if cache.exists():
        payload = json.loads(cache.read_text())
        if time.time() - payload["fetched_at"] < CACHE_TTL_SECONDS:
            return payload["rows"]
    try:
        rows = _scrape(market)
    except Exception:
        if cache.exists():  # fall back to stale cache rather than failing the run
            return json.loads(cache.read_text())["rows"]
        raise
    DATA_DIR.mkdir(exist_ok=True)
    cache.write_text(json.dumps({"fetched_at": time.time(), "rows": rows}, indent=1))
    return rows
