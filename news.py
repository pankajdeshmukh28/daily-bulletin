"""Headline collection via Google News RSS (no API key required)."""

import time
from urllib.parse import quote_plus

import feedparser

from config import MACRO_HEADLINES_PER_QUERY, MARKETS, TICKER_HEADLINES

_BASE = "https://news.google.com/rss/search"


def _rss(query: str, locale: dict, max_items: int) -> list[dict]:
    url = (
        f"{_BASE}?q={quote_plus(query)}+when:2d"
        f"&hl={locale['hl']}&gl={locale['gl']}&ceid={locale['ceid']}"
    )
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries[:max_items]:
        source = getattr(getattr(entry, "source", None), "title", "")
        items.append(
            {
                "title": entry.title,
                "source": source,
                "published": getattr(entry, "published", ""),
            }
        )
    return items


def macro_headlines(market: str) -> list[dict]:
    cfg = MARKETS[market]
    seen, items = set(), []
    for q in cfg["macro_queries"]:
        for item in _rss(q, cfg["google_news_locale"], MACRO_HEADLINES_PER_QUERY):
            if item["title"] not in seen:
                seen.add(item["title"])
                items.append(item)
        time.sleep(0.5)  # be polite to the RSS endpoint
    return items


def ticker_headlines(market: str, ticker: str, company_name: str) -> list[dict]:
    cfg = MARKETS[market]
    # Company name matches news better than the raw symbol (esp. for .NS tickers).
    query = f'"{company_name}" stock'
    return _rss(query, cfg["google_news_locale"], TICKER_HEADLINES)
