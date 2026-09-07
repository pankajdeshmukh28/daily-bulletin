"""Render the analysis into a markdown report + raw JSON, saved under reports/."""

import json

from config import MARKETS, REPORTS_DIR

DISCLAIMER = (
    "*Automated, news-driven research digest for personal use — informational "
    "only, not financial advice. Signals are model-generated estimates from "
    "headlines and price action and can be wrong; do your own research.*"
)

_STARS = {n: "★" * n + "☆" * (5 - n) for n in range(1, 6)}


def render_markdown(market: str, context: dict, analysis: dict) -> str:
    cfg = MARKETS[market]
    lines = [f"# Daily Signal — {cfg['label']} — {context['date']}", ""]
    idx = context.get("index")
    if idx:
        lines += [
            f"**{cfg['index_name']}**: {idx['close']} "
            f"({idx['pct_1d']:+.2f}% 1d, {idx['pct_5d']:+.2f}% 5d)",
            "",
        ]
    lines += ["## Market summary", "", analysis["market_summary"], ""]
    if analysis.get("market_summary_plain"):
        lines += [f"*In plain words: {analysis['market_summary_plain']}*", ""]
    lines += ["## Buy candidates", ""]
    for i, p in enumerate(analysis["picks"], 1):
        stars = _STARS.get(int(p["conviction"]), str(p["conviction"]))
        lines += [f"### {i}. {p['ticker']} — {p['name']}  ({stars})", ""]
        if p.get("plain_english"):
            lines += [f"*{p['plain_english']}*", ""]
        lines += [
            f"**Thesis:** {p['thesis']}",
            "",
            f"**Catalysts:** {p['catalysts']}",
            "",
            f"**Risks:** {p['risks']}",
            "",
            f"**Horizon:** {p['time_horizon']}",
            "",
        ]
    if analysis.get("etf_picks"):
        lines += ["## Fund ideas (ETFs)", ""]
        for p in analysis["etf_picks"]:
            stars = _STARS.get(int(p["conviction"]), str(p["conviction"]))
            lines += [f"### {p['ticker']} — {p['name']}  ({stars})", ""]
            if p.get("plain_english"):
                lines += [f"*{p['plain_english']}*", ""]
            lines += [f"**Thesis:** {p['thesis']}", "", f"**Risks:** {p['risks']}", ""]
    if analysis.get("watchlist"):
        lines += ["## Watchlist", ""]
        lines += [f"- **{w['ticker']}** ({w['name']}): {w['reason']}" for w in analysis["watchlist"]]
        lines.append("")
    if analysis.get("avoid"):
        lines += ["## Avoid — and why", ""]
        for a in analysis["avoid"]:
            lines.append(f"### {a['ticker']} — {a['name']}")
            lines.append("")
            if a.get("plain_english"):
                lines += [f"*{a['plain_english']}*", ""]
            lines += [f"**The evidence:** {a['reason']}", ""]
    lines += ["---", "", DISCLAIMER, ""]
    return "\n".join(lines)


def save(market: str, context: dict, analysis: dict) -> tuple[str, str]:
    REPORTS_DIR.mkdir(exist_ok=True)
    stem = f"{context['date']}_{market}"
    md_path = REPORTS_DIR / f"{stem}.md"
    json_path = REPORTS_DIR / f"{stem}.json"
    md_path.write_text(render_markdown(market, context, analysis))
    json_path.write_text(json.dumps({"context": context, "analysis": analysis}, indent=1))
    return str(md_path), str(json_path)
