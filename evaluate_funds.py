"""Mutual fund risk/return evaluation CLI.

Evaluate the curated starter list:
    .venv/bin/python evaluate_funds.py --market us
    .venv/bin/python evaluate_funds.py --market india

Evaluate any single fund on demand (US: ticker. India: mfapi scheme code —
find it with --search first):
    .venv/bin/python evaluate_funds.py --market us --fund FXAIX --name "Fidelity 500 Index"
    .venv/bin/python evaluate_funds.py --market india --search "quant small cap"
    .venv/bin/python evaluate_funds.py --market india --fund 120828 --name "Quant Small Cap Fund"

Every evaluation is saved to the fund_metrics table (db.py) whether it's
from the curated list or a one-off lookup.
"""

import argparse
import datetime as dt
import sys

import db
from config import MARKETS
from mutual_funds import evaluate_fund, search_india_fund


def _print_metrics(row: dict):
    print(f"\n{row['name']} ({row['fund_id']}) vs {row['benchmark']}, "
          f"{row['period_years']}y ({row['start_date']} to {row['end_date']}, "
          f"{row['trading_days_used']} trading days)")
    print(f"  Standard deviation : {row['std_dev']:>7.2f}%   (annualized volatility)")
    print(f"  Beta               : {row['beta']:>7.2f}    (sensitivity to {row['benchmark']})")
    print(f"  Alpha              : {row['alpha']:>7.2f}%   (excess return beyond what beta predicts)")
    print(f"  Sharpe ratio       : {row['sharpe']:>7.2f}    (return per unit of risk)")
    print(f"  R-squared          : {row['r_squared']:>7.1f}%   (how much beta/alpha can be trusted)")
    if row.get("explanation"):
        print(f"\n  {row['explanation']}")


def run_one(market: str, fund_id: str, name: str) -> dict:
    row = evaluate_fund(market, fund_id, name)
    row["date"] = dt.date.today().isoformat()
    db.save_fund_metrics(row)
    _print_metrics(row)
    return row


def run_curated(market: str):
    funds = MARKETS[market]["mutual_funds"]
    print(f"Evaluating {len(funds)} curated funds for {MARKETS[market]['label']}...")
    results, failures = [], []
    for f in funds:
        try:
            results.append(run_one(market, f["id"], f["name"]))
        except Exception as e:
            print(f"  SKIPPED {f['id']} ({f['name']}): {e}", file=sys.stderr)
            failures.append(f["id"])
    ranked = sorted(results, key=lambda r: r["sharpe"], reverse=True)
    print(f"\n== Ranked by Sharpe ratio ({MARKETS[market]['label']}) ==")
    for r in ranked:
        print(f"  {r['sharpe']:>6.2f}  {r['name']} ({r['fund_id']})")
    if failures:
        print(f"\n{len(failures)} fund(s) skipped: {failures}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Mutual fund risk/return evaluation")
    parser.add_argument("--market", choices=["us", "india"], required=True)
    parser.add_argument("--fund", help="ticker (US) or mfapi scheme code (India)")
    parser.add_argument("--name", default="", help="display name (optional for --fund)")
    parser.add_argument("--search", help="India only: free-text mfapi.in fund search")
    args = parser.parse_args()

    if args.search:
        if args.market != "india":
            parser.error("--search is only meaningful for --market india (mfapi.in)")
        for r in search_india_fund(args.search)[:20]:
            print(f"{r['scheme_code']:>8}  {r['scheme_name']}")
        return

    if args.fund:
        try:
            run_one(args.market, args.fund, args.name)
        except Exception as e:
            print(f"Could not evaluate {args.fund}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        run_curated(args.market)


if __name__ == "__main__":
    main()
