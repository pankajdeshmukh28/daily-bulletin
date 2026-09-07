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
    },
}

# How many top movers (each direction) get per-ticker news pulled.
TOP_MOVERS_PER_DIRECTION = 12
# Headlines per macro query / per ticker.
MACRO_HEADLINES_PER_QUERY = 8
TICKER_HEADLINES = 5
# How many buy candidates to ask Claude for.
NUM_PICKS = 10
# How many ETF/fund ideas to ask for.
NUM_ETF_PICKS = 3
