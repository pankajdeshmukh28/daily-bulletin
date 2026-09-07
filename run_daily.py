"""Daily entry point: python run_daily.py [--market us|india|both]

Per market: universe -> price snapshot -> top movers -> headlines ->
Claude analysis -> markdown + JSON report under reports/.
"""

import argparse
import datetime as dt
import sys

import config
from analyze import analyze
from news import macro_headlines, ticker_headlines
from notify import send_report, telegram_configured
from prices import index_snapshot, snapshot, top_movers
from report import save
from track import performance_context, record_picks
from universe import get_universe


def build_context(market: str) -> dict:
    cfg = config.MARKETS[market]
    universe = get_universe(market)
    names = {u["ticker"]: u["name"] for u in universe}
    print(f"[{market}] universe: {len(universe)} tickers; downloading prices...")

    snap = snapshot(list(names))
    print(f"[{market}] priced {len(snap)} tickers; fetching headlines...")
    movers = top_movers(snap, config.TOP_MOVERS_PER_DIRECTION)

    mover_rows = []
    for t in movers:
        mover_rows.append(
            {"ticker": t, "name": names[t], **snap[t],
             "headlines": ticker_headlines(market, t, names[t])}
        )
    etf_snap = snapshot([e["ticker"] for e in cfg["etfs"]])
    etf_rows = [{**e, **etf_snap[e["ticker"]]} for e in cfg["etfs"] if e["ticker"] in etf_snap]

    return {
        "date": dt.date.today().isoformat(),
        "market": market,
        "index": index_snapshot(cfg["index_ticker"]),
        "macro_headlines": macro_headlines(market),
        "movers": mover_rows,
        "etfs": etf_rows,
    }


def run(market: str, telegram: bool = True) -> str:
    context = build_context(market)
    context["track_record"] = performance_context(market)
    if context["track_record"]:
        print(f"[{market}] track record injected into prompt")
    print(f"[{market}] analyzing with {config.CLAUDE_MODEL}...")
    analysis = analyze(market, context)
    md_path, json_path = save(market, context, analysis)
    record_picks(market, context, analysis)
    print(f"[{market}] report: {md_path}")
    if telegram and telegram_configured():
        send_report(config.MARKETS[market]["label"], context, analysis, md_path)
        print(f"[{market}] sent to Telegram")
    return md_path


def main():
    parser = argparse.ArgumentParser(description="Daily stock signal digest")
    parser.add_argument("--market", choices=["us", "india", "both"], default="both")
    parser.add_argument("--no-telegram", action="store_true",
                        help="skip Telegram delivery even if configured")
    args = parser.parse_args()
    markets = ["us", "india"] if args.market == "both" else [args.market]
    failures = []
    for m in markets:
        try:
            run(m, telegram=not args.no_telegram)
        except Exception as e:  # one market failing shouldn't kill the other
            print(f"[{m}] FAILED: {e}", file=sys.stderr)
            failures.append(m)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
