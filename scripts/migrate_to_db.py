"""One-time migration: existing data/picks_log.jsonl + reports/*.json ->
Turso. Run once after setting up the DB, then the JSONL/JSON files are no
longer needed (kept git-ignored locally for reference only).
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
from config import DATA_DIR, REPORTS_DIR


def migrate_picks():
    log_path = DATA_DIR / "picks_log.jsonl"
    if not log_path.exists():
        print("no picks_log.jsonl found, skipping")
        return
    rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    by_market_date = defaultdict(list)
    for r in rows:
        by_market_date[(r["market"], r["date"])].append({
            "ticker": r["ticker"], "name": r.get("name", ""),
            "kind": "etf" if r.get("signal_type") == "etf" else "stock",
            "conviction": r["conviction"],
            "signal_type": r.get("signal_type", "untagged"),
            "entry_close": r["entry_close"],
            "index_entry_close": r.get("index_entry_close"),
        })
    for (market, date), picks in by_market_date.items():
        db.save_picks(market, date, picks)
    print(f"migrated {len(rows)} picks across {len(by_market_date)} (market, date) runs")


def migrate_reports():
    n = 0
    for path in sorted(REPORTS_DIR.glob("*_*.json")):
        stem = path.stem  # e.g. 2026-09-06_us
        date, market = stem.rsplit("_", 1)
        if market not in ("us", "india"):
            continue
        payload = json.loads(path.read_text())
        analysis = payload.get("analysis", payload)
        db.save_report(market, date, analysis)
        n += 1
    print(f"migrated {n} reports")


if __name__ == "__main__":
    migrate_picks()
    migrate_reports()
