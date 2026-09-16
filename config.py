"""Shared configuration for the stock signal bot."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
REPORTS_DIR = PROJECT_DIR / "reports"

# Load this project's .env first; fall back to the video pipeline's .env so
# the already-configured ANTHROPIC_API_KEY / TELEGRAM_* keys are picked up
# without duplicating them (load_dotenv never overrides already-set values).
load_dotenv(PROJECT_DIR / ".env")
_fallback_env = PROJECT_DIR.parent.parent / "toddler-video-pipeline" / ".env"
if _fallback_env.exists():
    load_dotenv(_fallback_env)

CLAUDE_MODEL = "claude-sonnet-5"

MARKETS = {
    "us": {
        "label": "US — S&P 500",
        "index_ticker": "^GSPC",
        "index_name": "S&P 500",
        "google_news_locale": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        "macro_queries": [
            "stock market today",
            "S&P 500",
            "Federal Reserve interest rates",
            "US economy inflation",
        ],
        "etfs": [
            {"ticker": "SPY", "name": "SPDR S&P 500", "theme": "whole US market"},
            {"ticker": "QQQ", "name": "Invesco QQQ", "theme": "big tech"},
            {"ticker": "IWM", "name": "iShares Russell 2000", "theme": "small companies"},
            {"ticker": "SMH", "name": "VanEck Semiconductor", "theme": "chip makers"},
            {"ticker": "XLK", "name": "Technology Select SPDR", "theme": "technology"},
            {"ticker": "XLE", "name": "Energy Select SPDR", "theme": "oil & energy"},
            {"ticker": "XLF", "name": "Financial Select SPDR", "theme": "banks & finance"},
            {"ticker": "XLV", "name": "Health Care Select SPDR", "theme": "healthcare"},
            {"ticker": "XLI", "name": "Industrial Select SPDR", "theme": "industrials"},
            {"ticker": "XLP", "name": "Consumer Staples SPDR", "theme": "everyday goods"},
            {"ticker": "XLY", "name": "Consumer Discretionary SPDR", "theme": "shopping & leisure"},
            {"ticker": "XLU", "name": "Utilities Select SPDR", "theme": "utilities"},
            {"ticker": "GLD", "name": "SPDR Gold Shares", "theme": "gold"},
            {"ticker": "TLT", "name": "iShares 20+ Year Treasury", "theme": "US government bonds"},
        ],
        # yfinance ticker == fund identifier for US mutual funds (unlike India,
        # they trade like any other symbol, no separate NAV lookup needed).
        "mutual_funds": [
            {"id": "FXAIX", "name": "Fidelity 500 Index Fund"},
            {"id": "VTSAX", "name": "Vanguard Total Stock Market Index Admiral"},
            {"id": "VFIAX", "name": "Vanguard 500 Index Admiral"},
            {"id": "FCNTX", "name": "Fidelity Contrafund"},
            {"id": "VWELX", "name": "Vanguard Wellington Fund"},
        ],
        # Annualized risk-free rate for Sharpe/alpha. US: pulled live from
        # yfinance's ^IRX (13-week T-bill yield) in mutual_funds.py; this is
        # only the fallback if that fetch fails.
        "risk_free_rate_fallback": 0.045,
    },
    "india": {
        "label": "India — Nifty 50",
        "index_ticker": "^NSEI",
        "index_name": "Nifty 50",
        "google_news_locale": {"hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
        "macro_queries": [
            "Indian stock market today",
            "Nifty 50 Sensex",
            "RBI monetary policy",
            "India economy",
        ],
        "etfs": [
            {"ticker": "NIFTYBEES.NS", "name": "Nippon Nifty 50 BeES", "theme": "whole Indian market"},
            {"ticker": "JUNIORBEES.NS", "name": "Nippon Nifty Next 50 BeES", "theme": "next-tier large companies"},
            {"ticker": "BANKBEES.NS", "name": "Nippon Nifty Bank BeES", "theme": "banks"},
            {"ticker": "ITBEES.NS", "name": "Nippon Nifty IT BeES", "theme": "IT services"},
            {"ticker": "PHARMABEES.NS", "name": "Nippon Nifty Pharma BeES", "theme": "pharma"},
            {"ticker": "CPSEETF.NS", "name": "Nippon CPSE ETF", "theme": "government-owned companies"},
            {"ticker": "GOLDBEES.NS", "name": "Nippon Gold BeES", "theme": "gold"},
            {"ticker": "SILVERBEES.NS", "name": "Nippon Silver BeES", "theme": "silver"},
            {"ticker": "MON100.NS", "name": "Motilal Oswal Nasdaq 100", "theme": "US big tech (from India)"},
        ],
        # mfapi.in scheme codes (Direct Plan, Growth option — the standard
        # choice: lowest expense ratio, no dividend-payout NAV drag). India
        # mutual funds have no market ticker, unlike US ones — see mutual_funds.py.
        "mutual_funds": [
            {"id": "122639", "name": "Parag Parikh Flexi Cap Fund"},
            {"id": "118955", "name": "HDFC Flexi Cap Fund"},
            {"id": "118825", "name": "Mirae Asset Large Cap Fund"},
            {"id": "120586", "name": "ICICI Prudential Large Cap Fund"},
        ],
        # RBI repo rate as of ~Sept 2026 — no free live daily source found;
        # update this manually when it changes (same pattern as the ElevenLabs
        # voice ID in the video pipeline: a hand-maintained constant).
        "risk_free_rate_fallback": 0.055,
    },
}

# Years of daily-return history used for the fund risk metrics.
FUND_METRICS_LOOKBACK_YEARS = 3

# How many top movers (each direction) get per-ticker news pulled.
TOP_MOVERS_PER_DIRECTION = 12
# Headlines per macro query / per ticker.
MACRO_HEADLINES_PER_QUERY = 8
TICKER_HEADLINES = 5
# How many buy candidates to ask Claude for.
NUM_PICKS = 10
# How many ETF/fund ideas to ask for.
NUM_ETF_PICKS = 3
