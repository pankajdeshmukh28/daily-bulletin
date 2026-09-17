"""Pull a fresh snapshot from Turso for the dashboard Artifact's embedded
data. Run this, then re-publish dashboard.html with the resulting JSON
pasted into its DATA constant — the dashboard is a manually-refreshed
snapshot (see README's Web dashboard section for why).

    .venv/bin/python scripts/build_dashboard_data.py > /tmp/dashboard_data.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import track


def _latest_date(market: str) -> str | None:
    rows = db._rows_as_dicts(db._execute(
        "SELECT date FROM reports WHERE market = ? ORDER BY date DESC LIMIT 1", [market]
    ))
    return rows[0]["date"] if rows else None


def _latest_index(market: str) -> dict | None:
    rows = db._rows_as_dicts(db._execute(
        "SELECT * FROM market_snapshot WHERE market = ? AND role = 'index' "
        "ORDER BY date DESC LIMIT 1", [market]
    ))
    return rows[0] if rows else None


def build() -> dict:
    us_date, india_date = _latest_date("us"), _latest_date("india")
    picks_rows = db.load_picks()
    graded = track._grade_rows(picks_rows) if picks_rows else []
    rets = [g["return_pct"] for g in graded]
    alphas = [g["alpha_pct"] for g in graded if g["alpha_pct"] is not None]

    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
        "us": {"date": us_date, "index": _latest_index("us"),
               "report": db.load_report("us", us_date) if us_date else None},
        "india": {"date": india_date, "index": _latest_index("india"),
                  "report": db.load_report("india", india_date) if india_date else None},
        # Note: no fund_metrics here — the main dashboard doesn't show a
        # preloaded fund list (user feedback: too much unrequested info on
        # the main page). Fund detail lives on the separate Fund Ledger
        # page (scripts/fund_ledger.html), populated only on request.
        "scorecard": {
            "n": len(graded),
            "avg_return": round(track._avg(rets), 2),
            "avg_alpha": round(track._avg(alphas), 2),
            "beat_n": sum(1 for a in alphas if a > 0),
            "beat_total": len(alphas),
            "by_type": track._agg(graded, lambda g: g["signal_type"]),
            "by_conv": track._agg(graded, lambda g: g["conviction"]),
        },
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=1, default=str))
