"""Mutual fund risk/return evaluation: standard deviation, beta, alpha,
Sharpe ratio, and R-squared vs. the market benchmark.

Data sources (mutual funds have no unified live-price feed the way stocks
do, so each market needs its own):
- US: funds trade with a real ticker (FXAIX, VTSAX, ...) — same `yfinance`
  path already used for stocks/ETFs.
- India: funds have no market ticker at all. Uses mfapi.in — a free,
  no-auth API serving AMFI's official daily NAV history by scheme code
  (confirmed live: https://api.mfapi.in/mf/<scheme_code>).

All five metrics are computed from daily returns over a shared lookback
window against the market index (S&P 500 / Nifty 50), annualized.
"""

import datetime as dt
import os

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from anthropic import Anthropic

from claude_client import extract_text, require_complete
from config import CLAUDE_MODEL, FUND_METRICS_LOOKBACK_YEARS, MARKETS

MFAPI_BASE = "https://api.mfapi.in/mf"

EXPLAIN_SYSTEM_PROMPT = """\
You are explaining a mutual fund's risk/return statistics to someone who
manages their own investments but is NOT a quant — they've never studied
standard deviation, beta, alpha, Sharpe ratio, or R-squared in a classroom.
You are given a fund's name, its benchmark, and its five computed metrics.

Write ONE short paragraph (2-4 sentences) that makes sense of the numbers
TOGETHER, not a definitions list. Cover, in plain language:
- How bumpy a ride this fund is (standard deviation) and how it moves
  relative to the benchmark (beta) — combine these into one idea of "how
  much risk am I taking".
- Whether the fund earned its keep: did it beat what its risk level alone
  would predict (alpha), and was the reward worth the risk taken (Sharpe)?
- Critically: use R-squared to qualify how much to TRUST the beta/alpha
  reading. If R-squared is low (below ~70%), say plainly that this fund
  doesn't really move with the benchmark, so the beta/alpha comparison is
  less meaningful — don't just report R-squared as a number, explain what
  it means for trusting the rest.

Rules:
- Plain language, but not baby talk — common investing words are fine
  ("risk", "return", "outperform", "volatile", "benchmark"). Avoid dense
  jargon ("alpha generation", "tracking error", "factor exposure").
  Someone who reads this once should walk away knowing whether this looks
  like a steady tracker, a genuinely differentiated pick, or a fund whose
  numbers don't inspire confidence — and why.
- Reference the actual figures naturally in the sentence (e.g. "it moved
  about 30% more than the market" rather than just "high beta"), so a
  reader who DOES know the jargon still finds it accurate and useful.
- No bullet points, no headers, no restating the raw numbers as a list —
  the numbers are already shown alongside this text. Just the paragraph.
- Never give a buy/sell recommendation — this is risk-profile explanation,
  not advice.

Respond with ONLY the paragraph — no preamble, no markdown fences.
"""


def search_india_fund(query: str) -> list[dict]:
    """[{scheme_code, scheme_name}, ...] matching a free-text query."""
    resp = requests.get(f"{MFAPI_BASE}/search", params={"q": query}, timeout=20)
    resp.raise_for_status()
    return [{"scheme_code": r["schemeCode"], "scheme_name": r["schemeName"]}
            for r in resp.json()]


def _india_nav_series(scheme_code: str, years: int) -> pd.Series:
    resp = requests.get(f"{MFAPI_BASE}/{scheme_code}", timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload["data"]
    dates = [dt.datetime.strptime(r["date"], "%d-%m-%Y") for r in rows]
    navs = [float(r["nav"]) for r in rows]
    s = pd.Series(navs, index=pd.DatetimeIndex(dates)).sort_index()
    cutoff = dt.datetime.now() - dt.timedelta(days=365 * years)
    return s[s.index >= cutoff]


def resolve_fund_name(market: str, fund_id: str) -> str:
    """Auto-resolve a fund's display name so callers (the Fund Ledger page)
    don't need to ask the user to type it — one less form field. Falls back
    to the raw identifier if the lookup fails for any reason."""
    try:
        if market == "india":
            resp = requests.get(f"{MFAPI_BASE}/{fund_id}", timeout=20)
            resp.raise_for_status()
            return resp.json()["meta"]["scheme_name"]
        info = yf.Ticker(fund_id).info
        return info.get("longName") or info.get("shortName") or fund_id
    except Exception:
        return fund_id


def _yfinance_price_series(ticker: str, years: int) -> pd.Series:
    data = yf.download(ticker, period=f"{years}y", interval="1d",
                        progress=False, auto_adjust=True)
    if data.empty:
        return pd.Series(dtype=float)
    return data["Close"][ticker] if isinstance(data.columns, pd.MultiIndex) else data["Close"]


def get_risk_free_rate(market: str) -> float:
    """Annualized risk-free rate as a decimal (e.g. 0.045 = 4.5%)."""
    if market == "us":
        try:
            irx = yf.download("^IRX", period="5d", progress=False, auto_adjust=True)
            if not irx.empty:
                val = irx["Close"]["^IRX"] if isinstance(irx.columns, pd.MultiIndex) else irx["Close"]
                return float(val.dropna().iloc[-1]) / 100
        except Exception:
            pass
    return MARKETS[market]["risk_free_rate_fallback"]


def compute_metrics(fund_prices: pd.Series, benchmark_prices: pd.Series,
                     risk_free_annual: float) -> dict | None:
    """Align two price series on shared dates, compute daily returns, and
    derive std dev / beta / alpha / Sharpe / R-squared, all annualized.
    Returns None if there's not enough overlapping history to be meaningful.
    """
    df = pd.DataFrame({"fund": fund_prices, "bench": benchmark_prices}).dropna()
    if len(df) < 60:  # need a reasonable number of trading days
        return None
    returns = df.pct_change().dropna()
    r_f, r_b = returns["fund"], returns["bench"]

    trading_days = 252
    rf_daily = risk_free_annual / trading_days

    std_dev_annual = float(r_f.std(ddof=1) * np.sqrt(trading_days))
    variance_b = float(r_b.var(ddof=1))
    covariance = float(r_f.cov(r_b))
    beta = covariance / variance_b if variance_b > 0 else float("nan")
    correlation = float(r_f.corr(r_b))
    r_squared = correlation ** 2

    excess_fund_annual = (float(r_f.mean()) - rf_daily) * trading_days
    excess_bench_annual = (float(r_b.mean()) - rf_daily) * trading_days
    alpha_annual = excess_fund_annual - beta * excess_bench_annual
    sharpe = excess_fund_annual / std_dev_annual if std_dev_annual > 0 else float("nan")

    return {
        "std_dev": round(std_dev_annual * 100, 2),   # as % for readability
        "beta": round(beta, 2),
        "alpha": round(alpha_annual * 100, 2),        # as %
        "sharpe": round(sharpe, 2),
        "r_squared": round(r_squared * 100, 1),       # as %
        "trading_days_used": len(returns),
        "start_date": returns.index[0].date().isoformat(),
        "end_date": returns.index[-1].date().isoformat(),
    }


def explain_fund(row: dict) -> str:
    """Plain-English verdict tying the 5 metrics together for a non-quant
    reader, while staying accurate enough that a seasoned investor reading
    the same sentence still gets something out of it (see the digest's
    plain_english fields for the same calibration philosophy)."""
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = (
        f"Fund: {row['name']} ({row['fund_id']})\n"
        f"Benchmark: {row['benchmark']}\n"
        f"Standard deviation: {row['std_dev']}% annualized\n"
        f"Beta: {row['beta']}\n"
        f"Alpha: {row['alpha']}% annualized\n"
        f"Sharpe ratio: {row['sharpe']}\n"
        f"R-squared: {row['r_squared']}%\n"
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,  # short paragraph, but thinking tokens still eat into this
        system=EXPLAIN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    require_complete(response)
    return extract_text(response).strip()


def evaluate_fund(market: str, fund_id: str, name: str = "",
                   years: int = FUND_METRICS_LOOKBACK_YEARS, explain: bool = True) -> dict:
    """fund_id: a ticker for US (e.g. 'FXAIX'), a mfapi scheme code for
    India (e.g. '122639'). Returns metrics + metadata, or raises if there's
    not enough overlapping history against the benchmark.
    """
    cfg = MARKETS[market]
    # The index itself (^GSPC / ^NSEI) is always on yfinance regardless of
    # market — only individual mutual funds differ (India funds have no
    # ticker at all, hence mfapi.in for those specifically).
    benchmark = _yfinance_price_series(cfg["index_ticker"], years)
    fund = _yfinance_price_series(fund_id, years) if market == "us" else _india_nav_series(fund_id, years)

    metrics = compute_metrics(fund, benchmark, get_risk_free_rate(market))
    if metrics is None:
        raise ValueError(
            f"Not enough overlapping price history for {fund_id} vs "
            f"{cfg['index_name']} to compute metrics (need 60+ trading days)"
        )
    row = {"market": market, "fund_id": fund_id, "name": name or resolve_fund_name(market, fund_id),
           "benchmark": cfg["index_name"], "period_years": years, **metrics}
    row["explanation"] = explain_fund(row) if explain else ""
    return row
