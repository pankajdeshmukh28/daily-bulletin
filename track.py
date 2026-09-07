"""Pick performance tracking + the feedback loop into the daily analysis.

Every daily run records its picks to the DB (data/picks_log.jsonl's
successor — see db.py) with entry price + the model's declared signal_type.
Two consumers:

- grade() / `python track.py`: scorecard of every pick vs current prices and
  vs the index over the same window (alpha), broken down by signal type and
  conviction -> reports/scorecard.md (also printed for the Actions step
  summary).
- performance_context(market): compact text summary of the bot's own track
  record, injected into the Claude prompt each day so the analysis calibrates
  against what has actually been working.
"""

import datetime as dt

import db
from config import REPORTS_DIR


def record_picks(market: str, context: dict, analysis: dict):
    """Persist today's picks (with entry prices) to the DB. Called by run_daily.

    Idempotent per (date, market, ticker) via the DB's own UNIQUE constraint.
    """
    closes = {m["ticker"]: m["close"] for m in context["movers"]}
    closes |= {e["ticker"]: e["close"] for e in context.get("etfs", [])}
    idx = context.get("index")
    index_entry_close = idx["close"] if idx else None

    rows = []
    for p in analysis["picks"]:
        if p["ticker"] not in closes:
            continue  # model referenced a name outside the provided data
        rows.append({
            "ticker": p["ticker"], "name": p["name"], "kind": "stock",
            "conviction": int(p["conviction"]),
            "signal_type": p.get("signal_type", "other"),
            "entry_close": closes[p["ticker"]],
            "index_entry_close": index_entry_close,
        })
    for p in analysis.get("etf_picks", []):
        if p["ticker"] not in closes:
            continue
        rows.append({
            "ticker": p["ticker"], "name": p["name"], "kind": "etf",
            "conviction": int(p["conviction"]), "signal_type": "etf",
            "entry_close": closes[p["ticker"]],
            "index_entry_close": index_entry_close,
        })
    if rows:
        db.save_picks(market, context["date"], rows)


def _grade_rows(rows: list[dict]) -> list[dict]:
    """Attach return_pct / alpha_pct / days_held at current prices."""
    from config import MARKETS
    from prices import snapshot

    tickers = sorted({r["ticker"] for r in rows})
    index_tickers = sorted({MARKETS[r["market"]]["index_ticker"] for r in rows})
    snap = snapshot(tickers + index_tickers)
    today = dt.date.today()
    graded = []
    for r in rows:
        cur = snap.get(r["ticker"])
        idx_cur = snap.get(MARKETS[r["market"]]["index_ticker"])
        if not cur:
            continue
        ret = (cur["close"] / r["entry_close"] - 1) * 100
        alpha = None
        if idx_cur and r.get("index_entry_close"):
            alpha = ret - (idx_cur["close"] / r["index_entry_close"] - 1) * 100
        graded.append({
            **r,
            "now_close": cur["close"],
            "return_pct": round(ret, 2),
            "alpha_pct": round(alpha, 2) if alpha is not None else None,
            "days_held": (today - dt.date.fromisoformat(r["date"])).days,
        })
    return graded


def _avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _agg(graded: list[dict], key) -> list[tuple[str, int, float, float, int, int]]:
    """Group -> (label, n, avg_return, avg_alpha, n_beat, n_with_alpha)."""
    groups: dict[str, list[dict]] = {}
    for g in graded:
        groups.setdefault(str(key(g)), []).append(g)
    out = []
    for label, rows in sorted(groups.items()):
        alphas = [r["alpha_pct"] for r in rows if r["alpha_pct"] is not None]
        out.append((label, len(rows), _avg([r["return_pct"] for r in rows]),
                    _avg(alphas), sum(1 for a in alphas if a > 0), len(alphas)))
    return out


def performance_context(market: str, max_recent: int = 15) -> str | None:
    """The bot's own track record as prompt text, or None if no history yet."""
    rows = db.load_picks(market)
    if not rows:
        return None
    graded = _grade_rows(rows)
    if not graded:
        return None
    alphas = [g["alpha_pct"] for g in graded if g["alpha_pct"] is not None]
    beat = sum(1 for a in alphas if a > 0)
    lines = [
        f"Past picks graded at current prices: {len(graded)} total, "
        f"avg return {_avg([g['return_pct'] for g in graded]):+.2f}%, "
        f"avg alpha vs index {_avg(alphas):+.2f}%, "
        f"beat-the-index {beat}/{len(alphas)}.",
        "By signal type (n, avg return, avg alpha, beat-index):",
    ]
    for label, n, ret, alpha, nb, na in _agg(graded, lambda g: g["signal_type"]):
        lines.append(f"- {label}: n={n}, ret {ret:+.2f}%, alpha {alpha:+.2f}%, beat {nb}/{na}")
    lines.append("By conviction:")
    for label, n, ret, alpha, nb, na in _agg(graded, lambda g: g["conviction"]):
        lines.append(f"- conviction {label}: n={n}, ret {ret:+.2f}%, alpha {alpha:+.2f}%, beat {nb}/{na}")
    lines.append(f"Most recent picks (up to {max_recent}):")
    for g in sorted(graded, key=lambda g: g["date"], reverse=True)[:max_recent]:
        lines.append(
            f"- {g['date']} {g['ticker']} ({g['signal_type']}, conviction {g['conviction']}): "
            f"{g['return_pct']:+.2f}% in {g['days_held']}d"
            + (f", alpha {g['alpha_pct']:+.2f}%" if g["alpha_pct"] is not None else "")
        )
    return "\n".join(lines)


def grade() -> str | None:
    rows = db.load_picks()
    if not rows:
        print("No picks logged yet — run run_daily.py first.")
        return None
    print(f"Grading {len(rows)} picks...")
    graded = _grade_rows(rows)

    today = dt.date.today().isoformat()
    rets = [g["return_pct"] for g in graded]
    alphas = [g["alpha_pct"] for g in graded if g["alpha_pct"] is not None]
    winners = [a for a in alphas if a > 0]
    lines = [
        f"# Pick Scorecard — as of {today}",
        "",
        f"- Picks graded: **{len(graded)}**",
        f"- Average return since entry: **{_avg(rets):+.2f}%**",
        f"- Average alpha vs index: **{_avg(alphas):+.2f}%**",
        f"- Beat-the-index rate: **{len(winners)}/{len(alphas)}**" if alphas else "",
        "",
        "## By signal type",
        "",
        "| Signal type | Picks | Avg return | Avg alpha | Beat index |",
        "|---|---|---|---|---|",
    ]
    for label, n, ret, alpha, nb, na in _agg(graded, lambda g: g["signal_type"]):
        lines.append(f"| {label} | {n} | {ret:+.2f}% | {alpha:+.2f}% | {nb}/{na} |")
    lines += ["", "## By conviction", "",
              "| Conviction | Picks | Avg return | Avg alpha | Beat index |",
              "|---|---|---|---|---|"]
    for label, n, ret, alpha, nb, na in _agg(graded, lambda g: g["conviction"]):
        lines.append(f"| {label} | {n} | {ret:+.2f}% | {alpha:+.2f}% | {nb}/{na} |")
    lines += ["", "## All picks", "",
              "| Signal date | Market | Ticker | Type | Conv. | Entry | Now | Return | Alpha |",
              "|---|---|---|---|---|---|---|---|---|"]
    for g in sorted(graded, key=lambda g: (g["date"], g["market"])):
        alpha_s = f"{g['alpha_pct']:+.2f}%" if g["alpha_pct"] is not None else "—"
        lines.append(
            f"| {g['date']} | {g['market']} | {g['ticker']} | {g['signal_type']} "
            f"| {g['conviction']} | {g['entry_close']} | {g['now_close']} "
            f"| {g['return_pct']:+.2f}% | {alpha_s} |"
        )
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / "scorecard.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"Avg return {_avg(rets):+.2f}%, avg alpha {_avg(alphas):+.2f}% -> {out}")
    return str(out)


if __name__ == "__main__":
    grade()
